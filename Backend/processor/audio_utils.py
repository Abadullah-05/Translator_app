import subprocess
import os
import torch
import soundfile as sf
import librosa
import numpy as np
import noisereduce as nr
from pyannote.audio import Pipeline

import config

os.environ["HF_TOKEN"] = getattr(config, "HUGGINGFACE_TOKEN", "")

def preprocess_and_clean_audio(audio_path, output_dir="processor/temp_output"):
    try:
        os.makedirs(output_dir, exist_ok=True)
        y, sr = librosa.load(audio_path, sr=16000, mono=True)
        
        if len(y) == 0:
            return audio_path

        if np.max(np.abs(y)) > 0:
            y = y / np.max(np.abs(y)) * 0.95

        y_clean = nr.reduce_noise(y=y, sr=sr, stationary=True, prop_decrease=0.75)

        clean_path = os.path.join(output_dir, f"clean_{os.path.basename(audio_path)}")
        sf.write(clean_path, y_clean, sr)
        return clean_path
    except Exception as e:
        print(f"Warning in audio cleaning: {e}")
        return audio_path

def separate_audio(file_path, output_dir):
    cmd = [
        "demucs", 
        "--two-stems=vocals",
        "-n", "htdemucs_ft",
        file_path, 
        "-o", output_dir
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        
        possible_paths = [
            os.path.join(output_dir, "htdemucs_ft", base_name, "vocals.wav"),
            os.path.join(output_dir, "htdemucs_ft", base_name, "vocals.mp3"),
            os.path.join(output_dir, "htdemucs", base_name, "vocals.wav"),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
                
        print("Error: Vocals file not found!")
        return None
        
    except subprocess.CalledProcessError as e:
        print(f"Demucs execution error: {e.stderr.decode()}")
        return None
    except Exception as e:
        print(f"Error in Demucs separation: {e}")
        return None

def diarize_and_map_speakers(vocals_path):
    if not vocals_path or not os.path.exists(vocals_path):
        print("Error: Invalid vocals path!")
        return None, None

    try:
        hf_token = getattr(config, "HUGGINGFACE_TOKEN", "")
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token
        )
        
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        pipeline.to(device)
            
        data, sample_rate = sf.read(vocals_path, always_2d=True)
        waveform = torch.tensor(data.T, dtype=torch.float32)
        audio_input = {
            "waveform": waveform, 
            "sample_rate": sample_rate
        }
        
        diarization_result = pipeline(audio_input)
        
        annotation = None
        if hasattr(diarization_result, "itertracks"):
            annotation = diarization_result
        elif hasattr(diarization_result, "annotation"):
            annotation = diarization_result.annotation
        
        if annotation is None:
            print("Error: Could not extract diarization annotation!")
            return None, None

        session_segments = []
        speaker_registry = {}
        speaker_counter = 1

        for turn, _, speaker in annotation.itertracks(yield_label=True):
            if (turn.end - turn.start) < 0.3:
                continue
                
            if speaker not in speaker_registry:
                speaker_registry[speaker] = f"Speaker_{speaker_counter}"
                speaker_counter += 1
            
            mapped_speaker = speaker_registry[speaker]
            session_segments.append({
                "start": round(turn.start, 3),
                "end": round(turn.end, 3),
                "speaker": mapped_speaker,
                "speaker_id": mapped_speaker
            })
            
        return session_segments, speaker_registry

    except Exception as e:
        print(f"Diarization Error: {e}")
        return None, None