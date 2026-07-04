"""
tts_exotel.py — Murf Falcon TTS for Exotel (16-bit Linear PCM)
---------------------------------------------------------------
Exotel Voicebot expects raw 16-bit Linear PCM audio at 8000Hz.
This module generates PCM audio WITHOUT mu-law (ULAW) conversion.

Functions:
  - generate_pcm(text)         → Returns full PCM audio bytes (for greeting cache)
  - generate_pcm_stream(text)  → Async generator, yields PCM chunks in real-time
"""

import os
import json
import base64
import asyncio
import websockets
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────

MURF_API_KEY = os.getenv("MURF_API_KEY")

# India endpoint for lowest latency
MURF_WS_URL = "wss://in.api.murf.ai/v1/speech/stream-input"

# ─────────────────────────────────────────────────────────────
# VOICE MAP — Hindi + Indian English voices
# Full list: https://murf.ai/api/docs/voices-styles/voice-library
# ─────────────────────────────────────────────────────────────

VOICE_MAP = {
    "hi": {
        "voiceId": "Sunaina",     # Native Hindi female voice
        "locale": "hi-IN",
        "style": "Conversational",
    },
    "en": {
        "voiceId": "Anisha",      # Indian English female voice
        "locale": "en-IN",
        "style": "Conversational",
    },
    "gu": {
        "voiceId": "Lia",
        "locale": "gu-IN",
        "style": "Conversational",
    },
    "bn": {
        "voiceId": "Lia",
        "locale": "bn-IN",
        "style": "Conversational",
    },
    "mr": {
        "voiceId": "Lia",
        "locale": "mr-IN",
        "style": "Conversational",
    },
}


# ─────────────────────────────────────────────────────────────
# BATCH: Generate full PCM audio (for greeting cache)
# ─────────────────────────────────────────────────────────────

async def generate_pcm(text: str, lang_code: str = "hi") -> bytes:
    """
    Generate complete 16-bit PCM audio from text.
    Waits for all chunks, returns full audio blob.
    Used for pre-caching the greeting at server startup.
    """
    if not MURF_API_KEY:
        print("[ERR] MURF_API_KEY not set in .env!")
        return b""

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
            # Send voice config
            await ws.send(json.dumps({
                "voice_config": {
                    "voiceId": voice["voiceId"],
                    "locale":  voice["locale"],
                    "style":   voice["style"],
                    "rate":    0,
                    "pitch":   0,
                    "variation": 1
                }
            }))

            # Send text
            await ws.send(json.dumps({"text": text, "end": True}))

            # Collect all audio chunks
            while True:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
                except asyncio.TimeoutError:
                    break
                except json.JSONDecodeError:
                    continue

                if "audio" in msg:
                    audio_chunks.append(base64.b64decode(msg["audio"]))
                elif "error" in msg:
                    print(f"[ERR] Murf API Error: {msg['error']}")
                    return b""
                if msg.get("final"):
                    break

    except Exception as e:
        print(f"[ERR] Murf TTS error: {e}")
        return b""

    if not audio_chunks:
        print("[ERR] Murf returned no audio chunks")
        return b""

    # Combine and strip WAV header → raw 16-bit PCM
    combined = b"".join(audio_chunks)
    pcm = combined[44:] if combined.startswith(b"RIFF") else combined

    print(f"[OK] PCM audio ready: {len(pcm)} bytes")
    return pcm


# ─────────────────────────────────────────────────────────────
# STREAMING: Yield PCM chunks as they arrive from Murf
# Caller hears audio within ~130ms — no waiting!
# ─────────────────────────────────────────────────────────────

async def generate_pcm_stream(text: str, lang_code: str = "hi"):
    """
    STREAMING version — yields raw 16-bit PCM chunks as they arrive.
    No ULAW conversion (Exotel expects Linear PCM).
    """
    if not MURF_API_KEY:
        print("[ERR] MURF_API_KEY not set!")
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
            # Send voice config
            await ws.send(json.dumps({
                "voice_config": {
                    "voiceId": voice["voiceId"],
                    "locale":  voice["locale"],
                    "style":   voice["style"],
                    "rate":    0,
                    "pitch":   0,
                    "variation": 1
                }
            }))

            # Send text
            await ws.send(json.dumps({"text": text, "end": True}))

            # Stream audio chunks as they arrive
            while True:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
                except asyncio.TimeoutError:
                    print("[TIMEOUT] Murf stream timeout")
                    break
                except json.JSONDecodeError:
                    continue

                if "audio" in msg:
                    chunk = base64.b64decode(msg["audio"])

                    # Strip WAV header from first chunk only
                    if first_chunk and chunk.startswith(b"RIFF"):
                        chunk = chunk[44:]
                        first_chunk = False

                    # Ensure even byte count for 16-bit PCM
                    if len(chunk) % 2 != 0:
                        chunk = chunk[:-1]

                    if chunk:
                        total_bytes += len(chunk)
                        yield chunk  # Raw PCM — Exotel plays this directly

                elif "error" in msg:
                    print(f"[ERR] Murf API Error: {msg['error']}")
                    return

                if msg.get("final"):
                    break

        print(f"[OK] Streamed {total_bytes} PCM bytes")

    except Exception as e:
        print(f"[ERR] Murf stream error: {e}")
