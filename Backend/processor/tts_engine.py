import os
import numpy as np
import soundfile as sf
from elevenlabs import ElevenLabs

# --- CONFIG IMPORT ---
import config  # Root folder se config import kiya

# ElevenLabs client initialization using config.py
client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)

def ensure_min_duration(audio_path, min_duration_sec=40.0):
    """
    Yeh function check karta hai ki audio sample 40 second ka hai ya nahi.
    Agar 40 second se kam hai, toh use repeat (loop) karke 40 second ka bana deta hai.
    """
    try:
        data, samplerate = sf.read(audio_path)
        duration = len(data) / samplerate
        
        print(f"Checking sample duration for {os.path.basename(audio_path)}: {duration:.2f}s")
        
        if duration < min_duration_sec:
            print(f"⚠️ Sample is less than {min_duration_sec}s. Repeating/looping to reach 40 seconds...")
            
            repeats = int(np.ceil(min_duration_sec / duration))
            
            if data.ndim == 1:
                looped_data = np.tile(data, repeats)
                target_samples = int(min_duration_sec * samplerate)
                looped_data = looped_data[:target_samples]
            else:
                looped_data = np.tile(data, (repeats, 1))
                target_samples = int(min_duration_sec * samplerate)
                looped_data = looped_data[:target_samples, :]
                
            extended_path = audio_path.replace(".wav", "_extended40s.wav")
            sf.write(extended_path, looped_data, samplerate)
            print(f"✅ Audio successfully extended to 40s and saved at: {extended_path}")
            return extended_path
            
        return audio_path
    except Exception as e:
        print(f"Error in ensuring min duration: {e}")
        return audio_path

def clone_voice_from_audio(audio_path, voice_name="Video_Cloned_Speaker"):
    """
    Clones voice dynamically using ElevenLabs API after ensuring min duration.
    """
    try:
        processed_audio_path = ensure_min_duration(audio_path, min_duration_sec=40.0)
        
        print(f"Uploading audio to ElevenLabs for voice cloning: {processed_audio_path}")
        with open(processed_audio_path, "rb") as f:
            voice = client.clone(
                name=voice_name,
                files=[f],
                description="Dynamically cloned from video vocals sample."
            )
        
        # Cleanup temporary extended file if created
        if processed_audio_path != audio_path and os.path.exists(processed_audio_path):
            os.remove(processed_audio_path)
            
        voice_id = voice.voice_id if hasattr(voice, "voice_id") else voice.get("voice_id")
        print(f"✅ Voice cloned successfully! Dynamic Voice ID: {voice_id}")
        return voice_id
    except Exception as e:
        print(f"❌ Voice cloning error: {e}")
        return None

def delete_cloned_voices(voice_registry):
    """
    Deletes the dynamically created voice(s) from ElevenLabs after processing to save slots/cleanup.
    """
    try:
        if isinstance(voice_registry, dict):
            for speaker, voice_id in voice_registry.items():
                if voice_id and voice_id != "JBFqnCBsd6RMkjVDRZzb":
                    print(f"🗑️ Deleting cloned voice {voice_id} for {speaker}...")
                    client.voices.delete(voice_id=voice_id)
        elif isinstance(voice_registry, str):
            if voice_registry and voice_registry != "JBFqnCBsd6RMkjVDRZzb":
                print(f"🗑️ Deleting cloned voice ID: {voice_registry}...")
                client.voices.delete(voice_id=voice_registry)
    except Exception as e:
        print(f"❌ Error deleting cloned voices: {e}")

def generate_dubbed_audio(translated_segments, vocals_path, target_language: str):
    """
    Generates dubbed audio for each segment using dynamically cloned voice from vocals_path.
    Target language is now mandatory.
    """
    if not target_language or not target_language.strip() or target_language.lower() == "select target language":
        raise ValueError("Target language is required! Please select a valid target language.")
        
    print(f"Starting TTS generation with Dynamic Voice Cloning for Target Language: {target_language}...")
    
    dubbed_segments_audio = []
    voice_registry = {}
    
    # Step 1: Clone voice dynamically using the original video vocals
    print("Cloning voice from video vocals sample...")
    primary_voice_id = clone_voice_from_audio(vocals_path, voice_name=f"Cloned_{target_language}")
    
    if not primary_voice_id:
        print("⚠️ Voice cloning failed. Falling back to default voice ID.")
        primary_voice_id = "JBFqnCBsd6RMkjVDRZzb"
        
    # Register the voice ID so main.py can delete it later
    voice_registry["Speaker_1"] = primary_voice_id
    
    # Step 2: Generate TTS for each segment using the dynamically cloned Voice ID
    for segment in translated_segments:
        start = segment.get("start", 0.0)
        end = segment.get("end", 0.0)
        speaker_id = segment.get("speaker", segment.get("speaker_id", "Speaker_1"))
        text = segment.get("translated_text", "")
        
        if not text.strip():
            continue
            
        # Assign or reuse voice ID per speaker
        if speaker_id not in voice_registry:
            voice_registry[speaker_id] = primary_voice_id
            
        current_voice_id = voice_registry[speaker_id]
        
        try:
            print(f"Generating voice ({target_language}) for {speaker_id} [{current_voice_id}] ({start:.2f}s - {end:.2f}s)...")
            
            # ElevenLabs TTS API Call using multilingual model
            audio_stream = client.text_to_speech.convert(
                text=text,
                voice_id=current_voice_id,
                model_id="eleven_multilingual_v2",
                output_format="mp3_22050_32"
            )
            
            segment_audio_path = f"processor/temp_output/seg_{start}_{end}.mp3"
            os.makedirs(os.path.dirname(segment_audio_path), exist_ok=True)
            
            with open(segment_audio_path, "wb") as f:
                for chunk in audio_stream:
                    f.write(chunk)
                    
            dubbed_segments_audio.append({
                "start": start,
                "end": end,
                "audio_path": segment_audio_path,
                "speaker_id": speaker_id
            })
            
        except Exception as e:
            print(f"Error generating audio for segment: {e}")
            
    return dubbed_segments_audio, voice_registry