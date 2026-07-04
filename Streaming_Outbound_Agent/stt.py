import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("IVR_GROQ_API_KEY"))

def transcribe_audio(audio_bytes: bytes) -> str:
    """
    Transcribe audio bytes using Groq Whisper large-v3.
    Returns plain transcribed text string.
    """
    file_tuple = ("audio.mp3", audio_bytes)
    
    result = client.audio.transcriptions.create(
        model="whisper-large-v3-turbo",
        file=file_tuple,
        language="hi",
        prompt="website development, software development, digital marketing, mobile app",
        response_format="text"
    )

    if isinstance(result, str):
        return result.strip()
    return str(result).strip()