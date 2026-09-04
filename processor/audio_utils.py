import subprocess
import os
import torch
import soundfile as sf
from pyannote.audio import Pipeline

# --- HUGGING FACE TOKEN SETUP ---
os.environ["HF_TOKEN"] = "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"

# --- 1. Audio Separation (Demucs) ---
def separate_audio(file_path, output_dir):
    """
    Ye function Demucs ka use karke vocals aur background music ko alag karta hai.
    """
    print(f"Demucs processing started for: {file_path}")
    cmd = ["demucs", "--two-stems=vocals", file_path, "-o", output_dir]
    
    try:
        subprocess.run(cmd, check=True)
        print("Audio separation successful!")
        
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        vocals_path = os.path.join(output_dir, "htdemucs", base_name, "vocals.wav")
        
        if not os.path.exists(vocals_path):
            print(f"Error: Vocals file not found at {vocals_path}")
            return None
            
        return vocals_path
    except Exception as e:
        print(f"Error in Demucs: {e}")
        return None

# --- 2. Speaker Diarization & Mapping ---
def diarize_and_map_speakers(vocals_path):
    """
    Ye function Pyannote ka use karke identify karta hai ki kis speaker ne kab bola.
    """
    if not vocals_path or not os.path.exists(vocals_path):
        print("Error: Invalid vocals file path provided for diarization.")
        return None, None

    print(f"Starting Speaker Diarization for: {vocals_path}")
    try:
        pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1")
        
        if torch.cuda.is_available():
            pipeline.to(torch.device("cuda"))
            
        # Audio ko soundfile se read karke tensor dict mein convert karna
        data, sample_rate = sf.read(vocals_path, always_2d=True)
        waveform = torch.tensor(data.T, dtype=torch.float32)
        audio_input = {"waveform": waveform, "sample_rate": sample_rate}
        
        diarization_result = pipeline(audio_input)
        
        # --- SMART ANNOTATION EXTRACTOR ---
        annotation = None
        if hasattr(diarization_result, "itertracks"):
            annotation = diarization_result
        elif hasattr(diarization_result, "annotation"):
            annotation = diarization_result.annotation
        elif hasattr(diarization_result, "speaker_diarization"):
            annotation = diarization_result.speaker_diarization
        elif isinstance(diarization_result, dict):
            for k, v in diarization_result.items():
                if hasattr(v, "itertracks"):
                    annotation = v
                    break
        
        if annotation is None or not hasattr(annotation, "itertracks"):
            for attr in dir(diarization_result):
                try:
                    val = getattr(diarization_result, attr)
                    if hasattr(val, "itertracks"):
                        annotation = val
                        break
                except Exception:
                    continue
                    
        if annotation is None or not hasattr(annotation, "itertracks"):
            print(f"Error: Could not extract annotation/itertracks from type {type(diarization_result)}")
            return None, None

        session_segments = []
        speaker_registry = {}
        speaker_counter = 1

        for turn, _, speaker in annotation.itertracks(yield_label=True):
            if speaker not in speaker_registry:
                speaker_registry[speaker] = f"Speaker_{speaker_counter}"
                speaker_counter += 1
            
            mapped_speaker = speaker_registry[speaker]
            # Dono keys daal di hain taaki translation script ko jo chahiye wo mil jaye
            session_segments.append({
                "start": turn.start,
                "end": turn.end,
                "speaker": mapped_speaker,
                "speaker_id": mapped_speaker
            })
            
        print(f"Speaker Diarization successful! Found {len(speaker_registry)} speakers.")
        return session_segments, speaker_registry

    except Exception as e:
        print(f"Diarization Error: {e}")
        return None, None