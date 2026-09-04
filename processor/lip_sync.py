import subprocess
import os
from processor.tts_engine import delete_cloned_voices

def mix_audio_and_sync_video(original_video_path, background_audio_path, dubbed_segments_audio, output_video_path, speaker_voice_registry=None):
    """
    Ye function background audio aur dubbed segments ko mix karega, 
    aur Wav2Lip ki madad se final video banakar cloned voices ko delete kar dega.
    """
    print("Starting Audio Mixing & Lip Sync Process...")
    
    temp_dubbed_audio = "processor/temp_dubbed_output.mp3"
    
    with open(temp_dubbed_audio, "wb") as outfile:
        for seg in dubbed_segments_audio:
            outfile.write(seg["audio_bytes"])
            
    print("Dubbed audio combined successfully.")
    
    # Step B: FFmpeg se Dubbed Voice + Background Music ko mix karna
    final_mixed_audio = "processor/final_mixed_audio.mp3"
    
    mix_cmd = [
        "ffmpeg", "-y",
        "-i", temp_dubbed_audio,
        "-i", background_audio_path,
        "-filter_complex", "amix=inputs=2:duration=first",
        final_mixed_audio
    ]
    
    try:
        subprocess.run(mix_cmd, check=True)
        print("Background sound and dubbed voice mixed successfully!")
    except Exception as e:
        print(f"Error mixing audio with FFmpeg: {e}")
        return None

    # --- Step C: Wav2Lip Integration with Absolute Paths & Working Directory ---
    print("Running Wav2Lip for final video lip-sync...")
    
    wav2lip_dir = os.path.abspath("Backend/Wav2Lip")
    
    # Wav2Lip ke andar 'temp' folder banana zaroori hai taaki audio save ho sake
    os.makedirs(os.path.join(wav2lip_dir, "temp"), exist_ok=True)
    
    inference_script = os.path.join(wav2lip_dir, "inference.py")
    checkpoint_path = os.path.join(wav2lip_dir, "checkpoints", "wav2lip.pth")
    
    # Sabhi paths ko absolute bana rahe hain taaki koi error na aaye
    abs_face_path = os.path.abspath(original_video_path)
    abs_audio_path = os.path.abspath(final_mixed_audio)
    abs_outfile_path = os.path.abspath(output_video_path)
    
    cmd = [
        "python", inference_script,
        "--checkpoint_path", checkpoint_path,
        "--face", abs_face_path,
        "--audio", abs_audio_path,
        "--outfile", abs_outfile_path
    ]
    
    try:
        # cwd set karne se Wav2Lip apne andar ke temp folder ko aaram se access kar lega
        subprocess.run(cmd, check=True, cwd=wav2lip_dir)
        print(f"Final Lip-Synced Video generated successfully at: {output_video_path}")
        
        # Video bante hi temporary cloned voices ko delete kar do
        if speaker_voice_registry:
            delete_cloned_voices(speaker_voice_registry)
            
        return output_video_path
        
    except Exception as e:
        print(f"Error running Wav2Lip: {e}")
        if speaker_voice_registry:
            delete_cloned_voices(speaker_voice_registry)
        return None