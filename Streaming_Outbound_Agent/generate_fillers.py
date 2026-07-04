import os
import asyncio
import argparse
from tts import generate_audio_file, TTS_PROVIDER

async def main():
    if not os.path.exists("static"):
        os.makedirs("static")
        
    ext = "mp3" if TTS_PROVIDER == "elevenlabs" else "wav"
    
    fillers = {
        "hmm": "Hmm...",
        "achha": "अच्छा..."
    }
    
    for name, text in fillers.items():
        file_path = os.path.join("static", f"filler_{name}.{ext}")
        print(f"Generating {file_path} ...")
        await generate_audio_file(text, "hi", file_path)
        print(f"Done -> {file_path}")

if __name__ == "__main__":
    asyncio.run(main())
