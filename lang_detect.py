from langdetect import detect

LANG_CONFIG = {
    "hi": {
        "name": "Hindi",
        "murf_voice": "hi-IN-aarav",
        "groq_lang": "hi",
    },
    "en": {
        "name": "English",
        "murf_voice": "en-IN-rohan",
        "groq_lang": "en",
    },
    "gu": {
        "name": "Gujarati",
        "murf_voice": "gu-IN-voice-1",
        "groq_lang": "gu",
    },
    "bn": {
        "name": "Bengali",
        "murf_voice": "bn-IN-voice-1",
        "groq_lang": "bn",
    },
    "mr": {
        "name": "Marathi",
        "murf_voice": "mr-IN-voice-1",
        "groq_lang": "mr",
    },
}

def detect_language(text: str) -> dict:
    """Detect language from text, default to Hindi if unsure."""
    try:
        lang_code = detect(text)
        return LANG_CONFIG.get(lang_code, LANG_CONFIG["hi"])
    except Exception:
        return LANG_CONFIG["hi"]
