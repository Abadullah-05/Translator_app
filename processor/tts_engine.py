import os
import io
import librosa
import soundfile as sf
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

load_dotenv()

# Yahan apni asli ElevenLabs API key seedhi string mein daal do:
elevenlabs = ElevenLabs(api_key="sk_7010b25ee1dae6d33302dc946ae154ec0ff3f7024ec1a475")

def generate_dubbed_audio(translated_segments, vocals_path):
    """
    Ye function translated text aur Speaker Registry ka use karke 
    ElevenLabs se voice cloning aur TTS generate karega, 
    repeat speakers ki voice ID reuse karte hue. (Sample max 15 seconds limit ke sath)
    """
    print("Starting ElevenLabs Voice Cloning & TTS Generation...")
    
    speaker_voice_registry = {}  # {"Speaker_1": "voice_id_xyz", "Speaker_2": "voice_id_abc"}
    dubbed_segments_audio = []
    
    for segment in translated_segments:
        speaker_id = segment["speaker_id"]
        text = segment["translated_text"]
        start = segment["start"]
        end = segment["end"]
        
        # Check karo ki kya is speaker ki voice ID pehle se registry mein hai ya nahi
        if speaker_id not in speaker_voice_registry:
            print(f"New speaker detected: {speaker_id}. Cloning voice via ElevenLabs...")
            try:
                # Audio sample ko load karke max 15 seconds tak trim karna
                try:
                    y, sr = librosa.load(vocals_path, sr=None)
                    max_samples = 15 * sr
                    if len(y) > max_samples:
                        y = y[:max_samples]
                        print(f"Audio sample trimmed to 15 seconds for voice cloning.")
                    else:
                        print(f"Audio sample is less than 15 seconds ({len(y)/sr:.2f}s), using full sample.")
                    
                    buffer = io.BytesIO()
                    sf.write(buffer, y, sr, format='WAV')
                    buffer.seek(0)
                    sample_bytes = buffer.read()
                except Exception as audio_err:
                    print(f"Warning: Could not process audio with librosa ({audio_err}), using full raw file.")
                    with open(vocals_path, "rb") as f:
                        sample_bytes = f.read()
                
                # ElevenLabs Instant Voice Clone API call
                voice = elevenlabs.voices.ivc.create(
                    name=f"Clone_{speaker_id}",
                    files=[io.BytesIO(sample_bytes)]
                )
                
                # Registry mein save kar liya taaki aage repeat hone par yehi use ho
                speaker_voice_registry[speaker_id] = voice.voice_id
                print(f"Voice cloned successfully for {speaker_id} -> ID: {voice.voice_id}")
                
            except Exception as e:
                print(f"Error cloning voice for {speaker_id}: {e}")
                # Agar cloning fail ho toh ek default fallback voice ID de do
                speaker_voice_registry[speaker_id] = "JBFqnCBsd6RMkjVDRZzb" 
        
        # Purani ya nayi assigned voice ID ko fetch karna
        voice_id = speaker_voice_registry[speaker_id]
        
        # Text-to-Speech generation using assigned voice ID
        try:
            print(f"Generating TTS for {speaker_id} using Voice ID: {voice_id}")
            audio_stream = elevenlabs.text_to_speech.convert(
                text=text,
                voice_id=voice_id,
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128"
            )
            
            # Stream se audio bytes collect karna
            audio_bytes = b"".join([chunk for chunk in audio_stream if isinstance(chunk, bytes)])
            
            dubbed_segments_audio.append({
                "start": start,
                "end": end,
                "speaker_id": speaker_id,
                "audio_bytes": audio_bytes
            })
            
        except Exception as e:
            print(f"TTS Generation Error for {speaker_id}: {e}")
            
    print("All segments dubbed successfully!")
    return dubbed_segments_audio, speaker_voice_registry

def delete_cloned_voices(elevenlabs_client, speaker_voice_registry):
    """
    Ye function session ke dauran banayi gayi custom cloned voices ko 
    ElevenLabs se delete kar deta hai taaki voice limit full na ho.
    """
    print("Cleaning up temporary cloned voices from ElevenLabs...")
    for speaker_id, voice_id in speaker_voice_registry.items():
        # Default fallback voice ko delete nahi karna hai
        if voice_id == "JBFqnCBsd6RMkjVDRZzb":
            continue
        try:
            # ElevenLabs SDK ke zariye voice delete karna
            elevenlabs_client.voices.delete(voice_id=voice_id)
            print(f"Successfully deleted temporary voice for {speaker_id} (ID: {voice_id})")
        except Exception as e:
            print(f"Failed to delete voice {voice_id}: {e}")