import os
import openai
from dotenv import load_dotenv
from openai import OpenAI

# .env file se API keys load karna
load_dotenv()

# Option 1: Seedhi apni API key yahan string ke andar daal do (Sabse asaan aur turant chalne wala tareeka)
client = OpenAI(api_key="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")

# YA Option 2: Agar .env file use karni hai, toh sirf "OPENAI_API_KEY" likho:
# client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
def translate_segments(vocals_path, session_segments):
    """
    Ye function Whisper API ka use karke har speaker segment ke hisab se 
    audio ko transcribe/translate karega, timestamps aur session ID ko maintain rakhte hue.
    """
    print("Starting translation with OpenAI Whisper...")
    
    translated_results = []
    
    for segment in session_segments:
        start = segment["start"]
        end = segment["end"]
        speaker_id = segment["speaker_id"]
        
        try:
            # Har segment ke liye file ko alag se open karna taaki pointer ki dikkat na aaye
            with open(vocals_path, "rb") as audio_file:
                # Whisper API call (New client syntax)
                response = client.audio.translations.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text"
                )
            
            translated_results.append({
                "start": start,
                "end": end,
                "speaker_id": speaker_id,
                "translated_text": response
            })
            
            print(f"[{start:.2f}s - {end:.2f}s] {speaker_id}: Translated successfully!")
            
        except Exception as e:
            print(f"Error translating segment for {speaker_id}: {e}")
            
    return translated_results