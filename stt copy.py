import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def transcribe_audio(audio_file_path: str, language: str = "hi") -> str:
    """
    Transcribe audio using Groq Whisper large-v3-turbo.
    Returns plain transcribed text string.
    """
    with open(audio_file_path, "rb") as f:
        result = client.audio.transcriptions.create(
            model="whisper-large-v3-turbo",
            file=f,
            language=language,
            response_format="text"
        )

    # result is already a plain string in response_format="text"
    if isinstance(result, str):
        return result.strip()
    # Fallback if SDK returns object
    return str(result).strip()


if __name__ == "__main__":
    result = transcribe_audio("test.wav", language="hi")
    print(f"Transcribed: {result}")