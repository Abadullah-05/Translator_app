import os
import json
import difflib
import torch
from openai import OpenAI
from faster_whisper import WhisperModel

import config

client = OpenAI(api_key=config.OPENAI_API_KEY)

_whisper_model_instance = None

def get_whisper_model():
    global _whisper_model_instance
    if _whisper_model_instance is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        _whisper_model_instance = WhisperModel("large-v3", device=device, compute_type=compute_type)
    return _whisper_model_instance

LANG_CODES = {
    "english": "en", "hindi": "hi", "spanish": "es", "french": "fr",
    "german": "de", "japanese": "ja", "chinese": "zh", "portuguese": "pt",
    "italian": "it", "polish": "pl", "turkish": "tr", "dutch": "nl",
    "korean": "ko", "arabic": "ar", "swedish": "sv", "indonesian": "id",
    "filipino": "tl", "romanian": "ro", "ukrainian": "uk", "greek": "el",
    "czech": "cs", "danish": "da", "finnish": "fi", "bulgarian": "bg",
    "croatian": "hr", "slovak": "sk", "tamil": "ta", "telugu": "te",
    "kannada": "kn", "malayalam": "ml", "bengali": "bn", "marathi": "mr",
    "gujarati": "gu", "punjabi": "pa", "hungarian": "hu", "norwegian": "no",
    "vietnamese": "vi"
}

def clean_transcript_with_gpt(raw_text, original_language):
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": f"""You are an expert {original_language} transcription cleaner for movie dubbing.
Fix ONLY obvious phonetic errors, audio artifacts, or Whisper misinterpretations.
CRITICAL RULES:
- Do NOT alter proper nouns, character names, historical names, or poetic terms.
- Keep the exact original meaning intact.
- Do NOT translate. Return ONLY the cleaned {original_language} text."""
                },
                {
                    "role": "user",
                    "content": raw_text
                }
            ],
            temperature=0.0,
            max_tokens=500
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"GPT cleanup error: {e}")
        return raw_text

def translate_text_with_gpt(text, target_language, original_language):
    try:
        if target_language.strip().lower() == original_language.strip().lower():
            return text
            
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": f"""You are a professional film dubbing dialogue writer and cinematic translator. 
Translate the text from {original_language} to {target_language}.

CRITICAL INSTRUCTIONS FOR CINEMATIC DUBBING:
1. NEVER TRANSLATE LITERALLY: Capture emotional meaning, dramatic weight, and character tone suitable for high-quality movie dubbing.
2. ACTION & BATTLE CRIES: Action exclamations or commands (e.g., 'Pusu!', 'Ambush!', 'Attack!') must be translated into natural, strong action words in {target_language} (e.g. 'घात!', 'हमला!'), NEVER phonetically transliterated.
3. CONTEXT AWARENESS: Process Romanized/Hinglish keyboard edits accurately to their native {original_language} meaning. Keep historical/philosophical terms precise.
4. ZERO HALLUCINATION: Translate ONLY the provided dialogue. Do NOT add external quotes, extra sentences, or unrequested idioms.
5. Return ONLY the final translated dialogue text."""
                },
                {
                    "role": "user",
                    "content": text
                }
            ],
            temperature=0.2,
            max_tokens=500
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Translation error: {e}")
        return text

def find_speaker_for_segment(seg_mid, session_segments):
    if not session_segments:
        return "Speaker_1"
        
    for turn in session_segments:
        if turn.get("start", 0.0) <= seg_mid <= turn.get("end", 0.0):
            return turn.get("speaker", "Speaker_1")
    
    closest = min(
        session_segments,
        key=lambda t: min(
            abs(t.get("start", 0) - seg_mid),
            abs(t.get("end", 0) - seg_mid)
        ),
        default=None
    )
    if closest:
        return closest.get("speaker", "Speaker_1")
    return "Speaker_1"

def is_duplicate_segment(new_seg, existing_segments, threshold=0.80):
    if not existing_segments:
        return False
        
    last_seg = existing_segments[-1]
    if last_seg["speaker"] != new_seg["speaker"]:
        return False
    
    t1 = last_seg.get("original_text", last_seg.get("text", "")).strip().lower()
    t2 = new_seg.get("original_text", new_seg.get("text", "")).strip().lower()
    
    similarity = difflib.SequenceMatcher(None, t1, t2).ratio()
    if similarity > threshold or t1 in t2 or t2 in t1:
        if len(t2) > len(t1):
            last_seg["end"] = max(last_seg["end"], new_seg["end"])
            if "original_text" in last_seg:
                last_seg["original_text"] = new_seg.get("original_text", new_seg.get("text", ""))
            if "text" in last_seg:
                last_seg["text"] = new_seg.get("text", "")
        return True
    return False

def merge_consecutive_speaker_segments(segments):
    if not segments:
        return []
    merged = []
    current = segments[0].copy()
    
    for next_seg in segments[1:]:
        if next_seg["speaker"] == current["speaker"] and (next_seg["start"] - current["end"]) < 2.5:
            current["end"] = next_seg["end"]
            current["text"] = current["text"].strip() + " " + next_seg["text"].strip()
            if "original_text" in current and "original_text" in next_seg:
                current["original_text"] = current["original_text"].strip() + " " + next_seg["original_text"].strip()
        else:
            merged.append(current)
            current = next_seg.copy()
    merged.append(current)
    return merged

def transcribe_and_diarize_only(vocals_path, session_segments, original_language):
    orig_lower = original_language.strip().lower()
    lang_code = LANG_CODES.get(orig_lower, None) if orig_lower != "auto-detect" else None
    
    whisper_model = get_whisper_model()
    
    segments, _ = whisper_model.transcribe(
        vocals_path,
        language=lang_code,
        temperature=0.0,
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500)
    )

    all_whisper_segments = []
    for ws in segments:
        ws_text = ws.text.strip()
        if not ws_text or (ws.end - ws.start) < 0.2:
            continue
            
        all_whisper_segments.append({
            "start": round(ws.start, 3),
            "end": round(ws.end, 3),
            "text": ws_text
        })

    raw_results = []
    for seg in all_whisper_segments:
        seg_start = seg["start"]
        seg_end = seg["end"]
        seg_mid = (seg_start + seg_end) / 2.0
        assigned_speaker = find_speaker_for_segment(seg_mid, session_segments)
        
        new_seg = {
            "start": seg_start,
            "end": seg_end,
            "speaker": assigned_speaker,
            "speaker_id": assigned_speaker,
            "text": seg["text"]
        }
        if not is_duplicate_segment(new_seg, raw_results):
            raw_results.append(new_seg)

    merged_segments = merge_consecutive_speaker_segments(raw_results)
    
    for seg in merged_segments:
        seg["original_text"] = clean_transcript_with_gpt(seg["text"], original_language)
        seg["translated_text"] = translate_text_with_gpt(seg["original_text"], "English", original_language)
        
    return merged_segments

def translate_segments(vocals_path, session_segments, target_language: str, original_language: str = "Auto-Detect"):
    raw_segments = transcribe_and_diarize_only(vocals_path, session_segments, original_language)
    for seg in raw_segments:
        seg["translated_text"] = translate_text_with_gpt(seg.get("original_text", seg.get("text", "")), target_language, original_language)
    return raw_segments

def translate_preedited_segments(edited_segments, target_language, original_language):
    if not edited_segments:
        return []
        
    if target_language.strip().lower() == original_language.strip().lower():
        for seg in edited_segments:
            seg["translated_text"] = seg.get("original_text", seg.get("text", ""))
        return edited_segments

    for seg in edited_segments:
        current_text = seg.get("original_text", seg.get("text", ""))
        if current_text:
            seg["translated_text"] = translate_text_with_gpt(current_text, target_language, original_language)
        else:
            seg["translated_text"] = ""
            
    return edited_segments