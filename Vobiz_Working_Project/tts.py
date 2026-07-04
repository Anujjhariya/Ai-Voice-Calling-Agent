"""
tts.py — Murf Falcon TTS (WebSocket Streaming)
------------------------------------------------
Replaces the old Google Translate TTS hack.

What this does:
  1. Opens a WebSocket connection to Murf Falcon (India region = lowest latency for you)
  2. Sends voice config (Hindi or English voice based on detected language)
  3. Streams text → receives raw PCM audio chunks back in real time
  4. Converts audio to 8000Hz 16-bit PCM (the exact format Exotel needs)
  5. Returns audio bytes to main.py → which sends them to the caller

Murf Falcon specs:
  - Time to first audio: ~130ms
  - Model latency: ~55ms
  - Cost: $0.01 per minute of generated audio
  - India endpoint: wss://in.api.murf.ai/v1/speech/stream-input
"""

import os
import json
import base64
import asyncio
import shutil
import tempfile
import websockets
import imageio_ffmpeg
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────

MURF_API_KEY = os.getenv("IVR_MURF_API_KEY")  # Uses IVR_ prefix from Vobiz .env

# Using India endpoint for lowest latency from your Mumbai server
# Concurrency limit: 2 on India endpoint (upgrade plan for more)
# Switch to US-East (wss://us-east.api.murf.ai/...) if you need 15 concurrent calls
MURF_WS_URL = "wss://in.api.murf.ai/v1/speech/stream-input"

# Murf Falcon returns 24000 Hz audio by default
# We need to convert it to 8000 Hz for Exotel (mulaw/PCM format)
MURF_SAMPLE_RATE = 24000

# ─────────────────────────────────────────────────────────────
# VOICE MAP — one voice per language
# These are Murf Falcon voice IDs for Indian languages
# You can change these from: https://murf.ai/api/docs/voices-styles/voice-library
# ─────────────────────────────────────────────────────────────

VOICE_MAP = {
    "hi": {
        "voiceId": "hi-IN-sunaina",
        "locale": "hi-IN",
        "style": "Conversational",
    },
    "hi_happy": {
        "voiceId": "hi-IN-sunaina",
        "locale": "hi-IN",
        "style": "Happy",
    },
    "hi_professional": {
        "voiceId": "hi-IN-sunaina",
        "locale": "hi-IN",
        "style": "Professional",
    },
    "hi_male": {
        "voiceId": "hi-IN-karan",
        "locale": "hi-IN",
        "style": "Conversational",
    },
    "hi_male_excited": {
        "voiceId": "hi-IN-karan",
        "locale": "hi-IN",
        "style": "Excited",
    },
    "en": {
        "voiceId": "en-IN-anisha",
        "locale": "en-IN",
        "style": "Conversational",
    },
    "en_happy": {
        "voiceId": "en-IN-anisha",
        "locale": "en-IN",
        "style": "Happy",
    },
    "en_professional": {
        "voiceId": "en-IN-anisha",
        "locale": "en-IN",
        "style": "Professional",
    },
    "en_male": {
        "voiceId": "en-IN-samar",
        "locale": "en-IN",
        "style": "Conversational",
    },
    "gu": {
        "voiceId": "gu-IN-diya",
        "locale": "gu-IN",
        "style": "Conversational",
    },
    "bn": {
        "voiceId": "bn-IN-debarati",
        "locale": "bn-IN",
        "style": "Conversational",
    },
    "mr": {
        "voiceId": "mr-IN-prajakta",
        "locale": "mr-IN",
        "style": "Conversational",
    },
    "pa": {
        "voiceId": "pa-IN-harpreet",
        "locale": "pa-IN",
        "style": "Conversational",
    },
}

# ─────────────────────────────────────────────────────────────
# MAIN FUNCTION: Generate PCM audio bytes from text
# This is what main.py calls: pcm_bytes = await generate_pcm(text, lang_code)
# ─────────────────────────────────────────────────────────────

async def generate_pcm(text: str, lang_code: str = "hi", emotion: str = "Conversational") -> bytes:
    """
    Convert text to speech using Murf Falcon WebSocket API.
    Returns raw 8kHz ULAW bytes. Collects ALL audio first.
    
    Args:
        text: Text to convert to speech
        lang_code: Language code (e.g., "en", "en_happy", "hi_professional")
        emotion: Emotion style (Conversational, Happy, Professional, Excited, etc.)
    
    For real-time streaming, use generate_pcm_stream() instead.
    """
    if not MURF_API_KEY:
        print("❌ MURF_API_KEY not set in .env!")
        return b""

    # Extract emotion from lang_code if it contains one (e.g., "en_happy" -> "en", "Happy")
    if "_" in lang_code:
        base_lang, emotion_part = lang_code.split("_", 1)
        emotion = emotion_part.capitalize()  # "happy" -> "Happy"
        lang_code = base_lang

    voice = VOICE_MAP.get(lang_code, VOICE_MAP["hi"])
    ws_url = (
        f"{MURF_WS_URL}?api-key={MURF_API_KEY}"
        f"&model=FALCON&sample_rate=8000&channel_type=MONO&format=WAV"
    )
    audio_chunks = []

    try:
        async with websockets.connect(
            ws_url, ping_interval=20, ping_timeout=10, close_timeout=5
        ) as ws:
            await ws.send(json.dumps({
                "voice_config": {
                    "voiceId": voice["voiceId"], "locale": voice["locale"],
                    "style": emotion, "rate": 0, "pitch": 0, "variation": 1
                }
            }))
            await ws.send(json.dumps({"text": text, "end": True}))

            while True:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
                except (asyncio.TimeoutError, json.JSONDecodeError):
                    break
                if "audio" in msg:
                    audio_chunks.append(base64.b64decode(msg["audio"]))
                elif "error" in msg:
                    print(f"❌ Murf: {msg['error']}"); return b""
                if msg.get("final"):
                    break
    except Exception as e:
        print(f"❌ Murf TTS error: {e}"); return b""

    if not audio_chunks:
        return b""

    combined = b"".join(audio_chunks)
    pcm = combined[44:] if combined.startswith(b"RIFF") else combined
    import audioop
    ulaw = audioop.lin2ulaw(pcm, 2)
    print(f"✅ Audio ready: {len(ulaw)} bytes (emotion: {emotion})")
    return ulaw

async def generate_wav(text: str, lang_code: str = "hi", gender: str = "female", emotion: str = "Conversational") -> bytes:
    """
    Generate premium TTS using Murf and return standard WAV bytes.
    Used by the React web dashboard for online preview without phone calls.
    
    Args:
        text: Text to convert to speech
        lang_code: Language code (e.g., "en", "hi")
        gender: "female" or "male"
        emotion: Emotion style (Conversational, Happy, Professional, Excited, etc.)
    """
    if not MURF_API_KEY:
        return b""

    # Extract emotion from lang_code if it contains one (e.g., "en_happy" -> "en", "Happy")
    if "_" in lang_code and lang_code not in VOICE_MAP:
        parts = lang_code.split("_", 1)
        base_lang = parts[0]
        emotion_part = parts[1] if len(parts) > 1 else emotion
        emotion = emotion_part.capitalize()
        lang_code = base_lang
    
    voice_key = lang_code if gender == "female" else f"{lang_code}_male"
    voice = VOICE_MAP.get(voice_key, VOICE_MAP["hi"])
    
    ws_url = (
        f"{MURF_WS_URL}?api-key={MURF_API_KEY}"
        f"&model=FALCON&sample_rate=24000&channel_type=MONO&format=WAV"
    )
    audio_chunks = []

    try:
        async with websockets.connect(ws_url, ping_interval=20, ping_timeout=10, close_timeout=5) as ws:
            await ws.send(json.dumps({
                "voice_config": {
                    "voiceId": voice["voiceId"], "locale": voice["locale"],
                    "style": emotion, "rate": 0, "pitch": 0, "variation": 1
                }
            }))
            await ws.send(json.dumps({"text": text, "end": True}))

            while True:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=15.0))
                except (asyncio.TimeoutError, json.JSONDecodeError):
                    break
                if "audio" in msg:
                    audio_chunks.append(base64.b64decode(msg["audio"]))
                elif "error" in msg:
                    print(f"❌ Murf Preview Error: {msg['error']}")
                    return b""
                if msg.get("final"):
                    break
    except Exception as e:
        print(f"❌ Murf Preview exception: {e}")
        return b""

    if not audio_chunks:
        return b""

    return b"".join(audio_chunks)

async def generate_wav_stream(text: str, lang_code: str = "hi", gender: str = "female"):
    """
    Stream premium TTS using Murf and yield standard WAV bytes.
    Used by the React web dashboard for ZERO-LATENCY online previews!
    """
    if not MURF_API_KEY:
        return

    voice_key = lang_code if gender == "female" else f"{lang_code}_male"
    voice = VOICE_MAP.get(voice_key, VOICE_MAP["hi"])
    
    ws_url = (
        f"{MURF_WS_URL}?api-key={MURF_API_KEY}"
        f"&model=FALCON&sample_rate=24000&channel_type=MONO&format=WAV"
    )

    try:
        async with websockets.connect(ws_url, ping_interval=20, ping_timeout=10, close_timeout=5) as ws:
            await ws.send(json.dumps({
                "voice_config": {
                    "voiceId": voice["voiceId"], "locale": voice["locale"],
                    "style": voice["style"], "rate": 0, "pitch": 0, "variation": 1
                }
            }))
            await ws.send(json.dumps({"text": text, "end": True}))

            while True:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=15.0))
                except (asyncio.TimeoutError, json.JSONDecodeError):
                    break
                if "audio" in msg:
                    yield base64.b64decode(msg["audio"])
                elif "error" in msg:
                    print(f"❌ Murf Stream Error: {msg['error']}")
                    return
                if msg.get("final"):
                    break
    except Exception as e:
        print(f"❌ Murf Preview stream exception: {e}")


# ─────────────────────────────────────────────────────────────
# STREAMING FUNCTION: Yields ULAW chunks as they arrive from Murf
# This lets the caller hear audio within ~130ms (no waiting!)
# ─────────────────────────────────────────────────────────────

async def generate_pcm_stream(text: str, lang_code: str = "hi"):
    """
    STREAMING version — yields ULAW chunks as they arrive from Murf.
    Caller hears audio within ~130ms instead of waiting 3-5 seconds.
    """
    import audioop

    if not MURF_API_KEY:
        return

    voice = VOICE_MAP.get(lang_code, VOICE_MAP["hi"])
    ws_url = (
        f"{MURF_WS_URL}?api-key={MURF_API_KEY}"
        f"&model=FALCON&sample_rate=8000&channel_type=MONO&format=WAV"
    )
    first_chunk = True
    total_bytes = 0

    try:
        async with websockets.connect(
            ws_url, ping_interval=20, ping_timeout=10, close_timeout=5
        ) as ws:
            await ws.send(json.dumps({
                "voice_config": {
                    "voiceId": voice["voiceId"], "locale": voice["locale"],
                    "style": voice["style"], "rate": 0, "pitch": 0, "variation": 1
                }
            }))
            await ws.send(json.dumps({"text": text, "end": True}))

            while True:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=15.0))
                except asyncio.TimeoutError:
                    print("⏱️ Murf stream timeout — ending")
                    break
                except json.JSONDecodeError:
                    continue

                if "audio" in msg:
                    chunk = base64.b64decode(msg["audio"])
                    if first_chunk and chunk.startswith(b"RIFF"):
                        chunk = chunk[44:]
                        first_chunk = False
                    if len(chunk) % 2 != 0:
                        chunk = chunk[:-1]
                    if chunk:
                        ulaw_chunk = audioop.lin2ulaw(chunk, 2)
                        total_bytes += len(ulaw_chunk)
                        yield ulaw_chunk
                elif "error" in msg:
                    print(f"❌ Murf: {msg['error']}"); return
                if msg.get("final"):
                    break

        print(f"✅ Streamed {total_bytes} ULAW bytes")
    except Exception as e:
        print(f"❌ Murf stream error: {e}")


# ─────────────────────────────────────────────────────────────
# LEGACY FUNCTION — kept for backward compatibility
# stream_voice() was used in the old main.py (commented-out section)
# Now generate_pcm() is the main function used by the WebSocket server
# ─────────────────────────────────────────────────────────────

async def stream_voice(text: str, lang_code: str = "hi"):
    """
    Legacy function — yields audio chunks (MP3 format).
    Only used by the old HTTP-based main.py (now commented out).
    For the WebSocket server, use generate_pcm() instead.
    """
    # Just call generate_pcm and yield the result as one chunk
    # This keeps the old commented-out code from breaking if uncommented
    pcm_bytes = await generate_pcm(text, lang_code)
    if pcm_bytes:
        yield pcm_bytes


# ─────────────────────────────────────────────────────────────
# TEST — run this file directly to verify Murf is working
# Command: python tts.py
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    async def test():
        print("=" * 50)
        print("Testing Murf Falcon TTS")
        print("=" * 50)

        # Test 1: Hindi
        print("\n[Test 1] Hindi voice...")
        pcm = await generate_pcm(
            "Namaste! Main Binjva IT Solutions se bol rahi hoon. Aapki kya madad kar sakti hoon?",
            lang_code="hi"
        )
        if pcm:
            print(f"✅ Hindi test passed — {len(pcm)} PCM bytes")
        else:
            print("❌ Hindi test FAILED")

        # Test 2: English
        print("\n[Test 2] English voice...")
        pcm = await generate_pcm(
            "Hello! This is Binjva IT Solutions. How can I help you today?",
            lang_code="en"
        )
        if pcm:
            print(f"✅ English test passed — {len(pcm)} PCM bytes")
        else:
            print("❌ English test FAILED")

        # Test 3: Hindi-English mix (Hinglish — most common in India)
        print("\n[Test 3] Hinglish (Hindi + English mix)...")
        pcm = await generate_pcm(
            "Aapka appointment confirm ho gaya hai. Tuesday 3 PM ko milenge.",
            lang_code="hi"
        )
        if pcm:
            print(f"✅ Hinglish test passed — {len(pcm)} PCM bytes")
        else:
            print("❌ Hinglish test FAILED")

        print("\n" + "=" * 50)
        print("All tests done. If all 3 passed, Murf is ready.")
        print("=" * 50)

    asyncio.run(test())