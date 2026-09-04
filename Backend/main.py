from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import shutil
import os
import uvicorn

from processor.audio_utils import separate_audio, diarize_and_map_speakers
from processor.translator import translate_segments
from processor.tts_engine import generate_dubbed_audio
from processor.lip_sync import mix_audio_and_sync_video

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/translate")
async def handle_translation_pipeline(
    file: UploadFile = File(...),
    original_language: str = Form(...),
    target_language: str = Form(...)
):
    print(f"\n📡 File aayi: {file.filename}")
    print(f"🗣️ Original Lang: {original_language} | Target Lang: {target_language}")
    
    output_dir = "processor/temp_output"
    os.makedirs(output_dir, exist_ok=True)
    
    # File ko temporarily server par save karna
    video_path = os.path.join(output_dir, file.filename)
    with open(video_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        # Step 5: Demucs Audio Separation
        print("\n--- Step 5: Separating Vocals & Background ---")
        vocals_path = separate_audio(video_path, output_dir)
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        background_path = os.path.join(output_dir, "htdemucs", base_name, "no_vocals.wav")
        
        if not vocals_path:
            raise HTTPException(status_code=500, detail="Audio separation failed via Demucs.")
            
        # Step 5 (Contd): Speaker Diarization & Session Mapping
        print("\n--- Diarizing Speakers & Creating Sessions ---")
        session_segments, speaker_registry = diarize_and_map_speakers(vocals_path)
        
        if not session_segments:
            raise HTTPException(status_code=500, detail="Speaker diarization failed.")
            
        # Step 7: OpenAI Whisper Translation
        print("\n--- Step 7: Translating Segments via Whisper ---")
        translated_segments = translate_segments(vocals_path, session_segments)
        
        # Step 6 & 8: ElevenLabs Voice Cloning & TTS
        print("\n--- Step 8: Cloning Voices & Generating Dubbed Audio ---")
        dubbed_segments_audio, voice_registry = generate_dubbed_audio(translated_segments, vocals_path)
        
        # Step 9: Lip Sync & Final Merging
        print("\n--- Step 9: Lip Syncing and Final Merging ---")
        final_output = os.path.join(output_dir, "final_output_video.mp4")
        result_video = mix_audio_and_sync_video(
            original_video_path=video_path,
            background_audio_path=background_path,
            dubbed_segments_audio=dubbed_segments_audio,
            output_video_path=final_output
        )
        
        if result_video:
            return {
                "status": "success", 
                "message": "Video successfully dubbed and lip-synced!",
                "output_video": result_video
            }
        else:
            raise HTTPException(status_code=500, detail="Lip-sync or video merging failed.")

    except Exception as e:
        print(f"❌ Error in Pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download-video")
def download_video():
    video_path = "processor/temp_output/final_output_video.mp4"
    if os.path.exists(video_path):
        return FileResponse(video_path, media_type="video/mp4", filename="translated_video.mp4")
    raise HTTPException(status_code=404, detail="Video not found yet. Please process a video first.")

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)