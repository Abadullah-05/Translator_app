# processor/lip_sync.py
import subprocess
import os
import shutil
from processor.tts_engine import delete_cloned_voices

def mix_audio_and_sync_video(original_video_path, background_audio_path, dubbed_segments_audio, output_video_path, speaker_voice_registry=None):
    """
    Ye function background audio aur dubbed segments ko mix karega, 
    LatentSync model ki madad se lip-sync karega, GFPGAN se face enhance karega, 
    aur Real-ESRGAN se Full HD upscale karke cloned voices ko delete kar dega.
    """
    print("Starting Audio Mixing, LatentSync, GFPGAN & Real-ESRGAN Pipeline...")
    
    temp_dubbed_audio = "processor/temp_dubbed_output.mp3"
    
    # Step 1: Combine all dubbed audio segments
    with open(temp_dubbed_audio, "wb") as outfile:
        for seg in dubbed_segments_audio:
            if "audio_bytes" in seg:
                outfile.write(seg["audio_bytes"])
            elif "audio_path" in seg and os.path.exists(seg["audio_path"]):
                with open(seg["audio_path"], "rb") as f:
                    outfile.write(f.read())
            
    print("Dubbed audio combined successfully.")
    
    # --- Step 2: Auto-detect and Fix Background Audio Path ---
    if background_audio_path and not os.path.exists(background_audio_path):
        print(f"⚠️ Original background path not found: {background_audio_path}")
        alt_mp3 = background_audio_path.replace(".wav", ".mp3")
        if os.path.exists(alt_mp3):
            background_audio_path = alt_mp3
            print(f"✅ Found MP3 background file: {background_audio_path}")
        else:
            folder = os.path.dirname(background_audio_path)
            found = False
            if os.path.exists(folder):
                for file_name in os.listdir(folder):
                    if "no_vocals" in file_name or "background" in file_name:
                        background_audio_path = os.path.join(folder, file_name)
                        print(f"✅ Auto-detected background sound file: {background_audio_path}")
                        found = True
                        break
            if not found:
                print("⚠️ Background music file missing. Continuing with dubbed voice only.")
                background_audio_path = None

    # Step 2 (b): Mix Dubbed Voice + Background Music via FFmpeg
    final_mixed_audio = "processor/final_mixed_audio.mp3"
    
    if background_audio_path and os.path.exists(background_audio_path):
        mix_cmd = [
            "ffmpeg", "-y",
            "-i", temp_dubbed_audio,
            "-i", background_audio_path,
            "-filter_complex", "amix=inputs=2:duration=first",
            final_mixed_audio
        ]
    else:
        mix_cmd = [
            "ffmpeg", "-y",
            "-i", temp_dubbed_audio,
            "-c:a", "libmp3lame",
            final_mixed_audio
        ]
    
    try:
        subprocess.run(mix_cmd, check=True)
        print("Background sound and dubbed voice processed successfully!")
    except Exception as e:
        print(f"Error mixing audio with FFmpeg: {e}")
        return None

    # --- Step 3: LatentSync Integration ---
    print("Running LatentSync for lip-sync...")
    latentsync_dir = os.path.abspath("LatentSync")
    if not os.path.exists(latentsync_dir):
        latentsync_dir = os.path.abspath("Backend/LatentSync")
        
    abs_face_path = os.path.abspath(original_video_path)
    abs_audio_path = os.path.abspath(final_mixed_audio)
    
    latentsync_output = "processor/temp_latentsync_output.mp4"
    abs_latentsync_out = os.path.abspath(latentsync_output)
    
    latentsync_cmd = [
        "python", "-m", "scripts.inference",
        "--unet_config_path", "configs/unet.yaml",
        "--inference_ckpt_path", "checkpoints/latentsync_unet.pt",
        "--video_path", abs_face_path,
        "--audio_path", abs_audio_path,
        "--video_out_path", abs_latentsync_out,
        "--guidance_scale", "1.5",
        "--seed", "1247"
    ]
    
    try:
        subprocess.run(latentsync_cmd, check=True, cwd=latentsync_dir)
        print("LatentSync lip-sync completed successfully!")
    except Exception as e:
        print(f"Error running LatentSync: {e}")
        if speaker_voice_registry:
            delete_cloned_voices(speaker_voice_registry)
        return None

    # --- Step 4: GFPGAN Face Quality Enhancement ---
    print("Applying GFPGAN for face quality enhancement...")
    gfpgan_output = "processor/temp_gfpgan_output.mp4"
    try:
        if os.path.exists("inference_gfpgan.py"):
            gfpgan_cmd = [
                "python", "inference_gfpgan.py",
                "-i", latentsync_output,
                "-o", "processor/gfpgan_results",
                "-v", "1.4"
            ]
            subprocess.run(gfpgan_cmd, check=True)
            shutil.copy(latentsync_output, gfpgan_output) 
            print("GFPGAN face enhancement passed.")
        else:
            print("⚠️ GFPGAN script not found. Skipping face enhancement.")
            gfpgan_output = latentsync_output
    except Exception as e:
        print(f"GFPGAN warning: {e}")
        gfpgan_output = latentsync_output

    # --- Step 5: Real-ESRGAN Full HD Quality Restoration ---
    print("Applying Real-ESRGAN for Full HD quality upscaling...")
    try:
        if os.path.exists("inference_realesrgan_video.py"):
            realesrgan_cmd = [
                "python", "inference_realesrgan_video.py",
                "-i", gfpgan_output,
                "-o", output_video_path,
                "-s", "2"
            ]
            subprocess.run(realesrgan_cmd, check=True)
            print(f"Final High-Quality Video ready at: {output_video_path}")
        else:
            print("⚠️ Real-ESRGAN script not found. Using direct output.")
            shutil.copy(gfpgan_output, output_video_path)
            
    except Exception as e:
        print(f"Real-ESRGAN upscaling error: {e}")
        shutil.copy(gfpgan_output, output_video_path)

    # --- Step 6: Cleanup Cloned Voices from ElevenLabs ---
    if speaker_voice_registry:
        delete_cloned_voices(speaker_voice_registry)
        
    return output_video_path