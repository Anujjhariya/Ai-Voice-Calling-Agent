import os
import json
import base64
import asyncio
import websockets
import httpx
from dotenv import load_dotenv

load_dotenv()

MURF_API_KEY = os.getenv("IVR_MURF_API_KEY")
ELEVENLABS_API_KEY = os.getenv("IVR_ELEVENLABS_API_KEY")

MURF_WS_URL = "wss://in.api.murf.ai/v1/speech/stream-input"

# Murf Voice Map
MURF_VOICE_MAP = {
    "hi": {"voiceId": "hi-IN-sunaina", "locale": "hi-IN"},
    "en": {"voiceId": "en-IN-anisha", "locale": "en-IN"},
    "gu": {"voiceId": "gu-IN-diya", "locale": "gu-IN"},
    "mr": {"voiceId": "mr-IN-prajakta", "locale": "mr-IN"},
    "pa": {"voiceId": "pa-IN-harpreet", "locale": "pa-IN"},
}

# ElevenLabs Voice Map
ELEVENLABS_VOICE_MAP = {
    "hi": "Xb7hH8MSUJpSbSDYk0k2", # Alice
    "en": "JBFqnCBsd6RMkjVDRZzb", # George
}

TTS_PROVIDER = os.getenv("TTS_PROVIDER", "murf").lower()

async def generate_audio_file(text: str, lang_code: str = "hi", file_path: str = "output.wav"):
    """
    Legacy method used only for pre-generating the greeting during make_call.
    Saves the entire audio to a file.
    """
    if TTS_PROVIDER == "elevenlabs":
        await _generate_elevenlabs_file(text, lang_code, file_path)
    else:
        await _generate_murf_file(text, lang_code, file_path)

async def _generate_elevenlabs_file(text: str, lang_code: str, file_path: str):
    if not ELEVENLABS_API_KEY:
        return
    voice_id = ELEVENLABS_VOICE_MAP.get(lang_code, ELEVENLABS_VOICE_MAP["en"])
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": ELEVENLABS_API_KEY}
    data = {"text": text, "model_id": "eleven_multilingual_v2", "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, json=data, timeout=30.0)
            resp.raise_for_status()
            with open(file_path, "wb") as f:
                f.write(resp.content)
    except Exception as e:
        print(f"❌ ElevenLabs TTS exception: {e}")

async def _generate_murf_file(text: str, lang_code: str, file_path: str):
    if not MURF_API_KEY:
        return
    voice = MURF_VOICE_MAP.get(lang_code, MURF_VOICE_MAP["hi"])
    ws_url = f"{MURF_WS_URL}?api-key={MURF_API_KEY}&model=FALCON&sample_rate=8000&channel_type=MONO&format=WAV"
    audio_chunks = []
    try:
        async with websockets.connect(ws_url, ping_interval=None, ping_timeout=None) as ws:
            await ws.send(json.dumps({"voice_config": {"voiceId": voice["voiceId"], "locale": voice["locale"], "style": "Conversational", "rate": 0, "pitch": 0, "variation": 1}}))
            await ws.send(json.dumps({"text": text, "end": True}))
            while True:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=15.0))
                except (asyncio.TimeoutError, json.JSONDecodeError):
                    break
                if "audio" in msg:
                    audio_chunks.append(base64.b64decode(msg["audio"]))
                if msg.get("final"):
                    break
    except Exception as e:
        print(f"❌ Murf TTS exception: {e}")
    if audio_chunks:
        with open(file_path, "wb") as f:
            f.write(b"".join(audio_chunks))

# ─────────────────────────────────────────────────────────────
# NEW: DIRECT AUDIO STREAMING GENERATORS (FOR ZERO LATENCY)
# ─────────────────────────────────────────────────────────────

async def stream_tts_audio(text: str, lang_code: str = "hi"):
    """
    Yields audio chunks directly from the TTS provider's API.
    Used for FastAPI StreamingResponse.
    """
    if TTS_PROVIDER == "elevenlabs":
        async for chunk in _stream_elevenlabs(text, lang_code):
            yield chunk
    else:
        async for chunk in _stream_murf(text, lang_code):
            yield chunk

async def _stream_elevenlabs(text: str, lang_code: str):
    voice_id = ELEVENLABS_VOICE_MAP.get(lang_code, ELEVENLABS_VOICE_MAP["en"])
    # Use the streaming endpoint for ElevenLabs
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": ELEVENLABS_API_KEY}
    data = {"text": text, "model_id": "eleven_multilingual_v2", "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}
    
    try:
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", url, headers=headers, json=data) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size=1024):
                    yield chunk
    except Exception as e:
        print(f"❌ ElevenLabs Stream exception: {e}")

async def _stream_murf(text: str, lang_code: str):
    voice = MURF_VOICE_MAP.get(lang_code, MURF_VOICE_MAP["hi"])
    ws_url = f"{MURF_WS_URL}?api-key={MURF_API_KEY}&model=FALCON&sample_rate=8000&channel_type=MONO&format=WAV"
    try:
        async with websockets.connect(ws_url, ping_interval=None, ping_timeout=None) as ws:
            await ws.send(json.dumps({"voice_config": {"voiceId": voice["voiceId"], "locale": voice["locale"], "style": "Conversational", "rate": 0, "pitch": 0, "variation": 1}}))
            await ws.send(json.dumps({"text": text, "end": True}))
            while True:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=15.0))
                except (asyncio.TimeoutError, json.JSONDecodeError):
                    break
                if "audio" in msg:
                    yield base64.b64decode(msg["audio"])
                if msg.get("final"):
                    break
    except Exception as e:
        print(f"❌ Murf Stream exception: {e}")