from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
import shutil
import os
import uuid
import uvicorn
import subprocess
import base64
import json
import cv2

import config  # Config file for keys/settings

from processor.audio_utils import separate_audio, diarize_and_map_speakers
from processor.translator import transcribe_and_diarize_only, translate_preedited_segments, translate_segments
from processor.tts_engine import generate_dubbed_audio
from processor.lip_sync import mix_audio_and_sync_video

app = FastAPI(title="Neural Voice-Match Dubber Studio API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "processor/temp_output"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def cleanup_session_dir(session_dir: str):
    """Point #4 Fix: Safe background cleanup after download completes"""
    if os.path.exists(session_dir):
        shutil.rmtree(session_dir, ignore_errors=True)
        print(f"🧹 Cleaned up session directory: {session_dir}")

@app.post("/process-video")
async def process_video_pipeline(
    file: UploadFile = File(...),
    original_language: str = Form(...),
    target_language: str = Form(...),
    skip_review: str = Form("false")
):
    if not original_language or original_language.strip() == "" or original_language.lower() in ["auto-detect", "auto detect", "auto", "select original language"]:
        raise HTTPException(status_code=400, detail="Please select an original language before proceeding.")

    if not target_language or target_language.strip() == "" or target_language.lower() == "select target language":
        raise HTTPException(status_code=400, detail="Please select a target language before proceeding.")

    # Point #1 Fix: Unique Session Directory via UUID
    session_id = str(uuid.uuid4())
    session_dir = os.path.join(UPLOAD_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    print(f"\n📡 File aayi: {file.filename} | Session ID: {session_id}")
    print(f"🗣️ Original Lang: {original_language} | Target Lang: {target_language} | Skip Review: {skip_review}")
    
    video_path = os.path.join(session_dir, file.filename)
    with open(video_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        print("\n--- Separating Vocals & Background ---")
        vocals_path = separate_audio(video_path, session_dir)
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        background_path = os.path.join(session_dir, "htdemucs", base_name, "no_vocals.wav")
        
        if not vocals_path:
            raise HTTPException(status_code=500, detail="Audio separation failed via Demucs.")
            
        print("\n--- Diarizing Speakers & Creating Sessions ---")
        session_segments, speaker_registry = diarize_and_map_speakers(vocals_path)
        
        if not session_segments:
            raise HTTPException(status_code=500, detail="Speaker diarization failed.")
            
        is_skip = skip_review.lower() == "true"

        if is_skip:
            print(f"\n--- Skipping Review: Running Full Pipeline Directly ---")
            translated_segments = translate_segments(vocals_path, session_segments, target_language=target_language, original_language=original_language)
            dubbed_segments_audio, voice_registry = generate_dubbed_audio(translated_segments, vocals_path, target_language=target_language)
            
            final_output = os.path.join(session_dir, "final_output_video.mp4")
            
            # ✅ Yahan voice_registry pass kiya taaki cloned voices delete ho sakein
            result_video = mix_audio_and_sync_video(
                original_video_path=video_path,
                background_audio_path=background_path,
                dubbed_segments_audio=dubbed_segments_audio,
                output_video_path=final_output,
                speaker_voice_registry=voice_registry
            )
            
            if result_video:
                return {
                    "status": "success", 
                    "message": f"Video successfully dubbed to {target_language} directly!",
                    "skipped": True,
                    "session_id": session_id
                }
            else:
                raise HTTPException(status_code=500, detail="Lip-sync or video merging failed.")
        else:
            print(f"\n--- Extracting Original Whisper Transcript for Review ---")
            raw_transcript_segments = transcribe_and_diarize_only(vocals_path, session_segments, original_language=original_language)

            print("\n--- Extracting Speaker Face Thumbnails via OpenCV ---")
            speakers_dict = {}
            face_cascade = None
            try:
                cascade_path = os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml')
                if os.path.exists(cascade_path):
                    face_cascade = cv2.CascadeClassifier(cascade_path)
            except Exception as e:
                print(f"⚠️ Could not load Haar Cascade: {e}")

            for seg in raw_transcript_segments:
                speaker = seg.get("speaker", "Speaker_1")
                if speaker not in speakers_dict:
                    timestamp = seg.get("start", 0.0)
                    frame_filename = os.path.join(session_dir, f"face_{speaker}.jpg")
                    
                    ffmpeg_cmd = ["ffmpeg", "-y", "-ss", str(timestamp), "-i", video_path, "-vframes", "1", frame_filename]
                    subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                    base64_str = None
                    if os.path.exists(frame_filename):
                        img = cv2.imread(frame_filename)
                        if img is not None:
                            if face_cascade is not None and not face_cascade.empty():
                                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                                faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
                                
                                if len(faces) > 0:
                                    (x, y, w, h) = faces[0]
                                    pad = int(min(w, h) * 0.2)
                                    x1, y1 = max(0, x - pad), max(0, y - pad)
                                    x2, y2 = min(img.shape[1], x + w + pad), min(img.shape[0], y + h + pad)
                                    
                                    face_crop = img[y1:y2, x1:x2]
                                    if face_crop.size > 0:
                                        _, buffer = cv2.imencode('.jpg', face_crop)
                                        base64_str = base64.b64encode(buffer).decode('utf-8')
                            
                            if not base64_str:
                                _, buffer = cv2.imencode('.jpg', img)
                                base64_str = base64.b64encode(buffer).decode('utf-8')
                                
                        if os.path.exists(frame_filename):
                            os.remove(frame_filename)
                    
                    speakers_dict[speaker] = base64_str

            return JSONResponse(content={
                "skipped": False,
                "session_id": session_id,
                "speakers": speakers_dict,
                "transcript": raw_transcript_segments,
                "video_filename": file.filename
            })

    except Exception as e:
        print(f"❌ Error in Pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/translate-edited")
async def translate_edited_text(
    original_language: str = Form(...),
    target_language: str = Form(...),
    final_text: str = Form(...)
):
    """Point #3 Fix: Strict JSON parsing validation without dangerous fallback splits"""
    try:
        print(f"\n--- Translating User-Edited Original Text to {target_language} ---")
        try:
            edited_segments = json.loads(final_text)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON format provided in final_text.")
            
        translated_segments = translate_preedited_segments(edited_segments, target_language, original_language)
        return {"status": "success", "translated_transcript": translated_segments}
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"❌ Error in translate-edited: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate-dub")
async def generate_dub_pipeline(
    file: UploadFile = File(...),
    original_language: str = Form(...),
    target_language: str = Form(...),
    final_text: str = Form(...),
    session_id: str = Form(None)
):
    """Point #3 Fix: Strict JSON parsing validation for final dub generation"""
    session_dir = os.path.join(UPLOAD_DIR, session_id) if session_id else UPLOAD_DIR
    os.makedirs(session_dir, exist_ok=True)

    print(f"\n🎙️ Generating final dub to {target_language} from edited translation for file: {file.filename} (Session: {session_id})")
    
    video_path = os.path.join(session_dir, file.filename)
    if not os.path.exists(video_path):
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
    try:
        vocals_path = separate_audio(video_path, session_dir)
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        background_path = os.path.join(session_dir, "htdemucs", base_name, "no_vocals.wav")
        
        if not vocals_path:
            raise HTTPException(status_code=500, detail="Audio separation failed.")
            
        try:
            translated_segments = json.loads(final_text)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON format in edited translation segments.")
        
        print(f"\n--- Generating Dubbed Audio in {target_language} ---")
        dubbed_segments_audio, voice_registry = generate_dubbed_audio(translated_segments, vocals_path, target_language=target_language)
        
        print("\n--- Lip Syncing and Final Merging ---")
        final_output = os.path.join(session_dir, "final_output_video.mp4")
        
        # ✅ Yahan bhi voice_registry pass kiya hai manual dub generation ke baad cleanup ke liye
        result_video = mix_audio_and_sync_video(
            original_video_path=video_path,
            background_audio_path=background_path,
            dubbed_segments_audio=dubbed_segments_audio,
            output_video_path=final_output,
            speaker_voice_registry=voice_registry
        )
        
        if result_video:
            return {
                "status": "success",
                "message": f"Dubbed to {target_language} and lip-synced successfully!",
                "output_video": result_video,
                "session_id": session_id
            }
        else:
            raise HTTPException(status_code=500, detail="Lip-sync or video merging failed.")

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"❌ Error in generate-dub: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download-video")
def download_video(session_id: str = None, background_tasks: BackgroundTasks = None):
    """Point #4 Fix: Stream video and auto-cleanup session folder via BackgroundTasks"""
    if session_id:
        video_path = os.path.join(UPLOAD_DIR, session_id, "final_output_video.mp4")
        session_dir = os.path.join(UPLOAD_DIR, session_id)
    else:
        video_path = os.path.join(UPLOAD_DIR, "final_output_video.mp4")
        session_dir = None
        
    if os.path.exists(video_path):
        if session_dir and background_tasks:
            # Trigger cleanup only AFTER file response has streamed successfully
            background_tasks.add_task(cleanup_session_dir, session_dir)
        return FileResponse(video_path, media_type="video/mp4", filename="translated_video.mp4")
        
    raise HTTPException(status_code=404, detail="Video not found yet or session expired.")

if __name__ == "__main__":
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=True)