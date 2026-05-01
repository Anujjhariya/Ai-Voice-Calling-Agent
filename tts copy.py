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

MURF_API_KEY = os.getenv("MURF_API_KEY")

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
        "voiceId": "Sunaina",     # ✅ Native Hindi female voice
        "locale": "hi-IN",
        "style": "Conversation",
    },
    "en": {
        "voiceId": "Anisha",      # ✅ Indian English female voice
        "locale": "en-IN",
        "style": "Conversation",
    },
    "gu": {
        "voiceId": "Lia",         # ✅ Female — supports gu-IN
        "locale": "gu-IN",
        "style": "Conversation",
    },
    "bn": {
        "voiceId": "Lia",         # ✅ Female — supports bn-IN natively
        "locale": "bn-IN",
        "style": "Conversation",
    },
    "mr": {
        "voiceId": "Lia",         # ✅ Female — supports mr-IN
        "locale": "mr-IN",
        "style": "Conversation",
    },
}

# ─────────────────────────────────────────────────────────────
# MAIN FUNCTION: Generate PCM audio bytes from text
# This is what main.py calls: pcm_bytes = await generate_pcm(text, lang_code)
# ─────────────────────────────────────────────────────────────

async def generate_pcm(text: str, lang_code: str = "hi") -> bytes:
    """
    Convert text to speech using Murf Falcon WebSocket API.
    Returns raw 8000Hz 16-bit PCM bytes (what Exotel expects).
    
    Steps:
      1. Connect to Murf Falcon via WebSocket
      2. Send voice config + text
      3. Collect all audio chunks (WAV format, 24kHz)
      4. Convert from 24kHz WAV → 8kHz raw PCM using ffmpeg
    """
    if not MURF_API_KEY:
        print("❌ MURF_API_KEY not set in .env!")
        return b""

    voice = VOICE_MAP.get(lang_code, VOICE_MAP["hi"])
    
    # Build WebSocket URL with query params
    # format=WAV so we can detect and strip the WAV header
    ws_url = (
        f"{MURF_WS_URL}"
        f"?api-key={MURF_API_KEY}"
        f"&model=FALCON"
        f"&sample_rate=8000"
        f"&channel_type=MONO"
        f"&format=WAV"
    )

    # Collect all audio bytes here
    audio_chunks = []
    first_chunk = True  # WAV header is only in the first chunk — we skip 44 bytes

    try:
        async with websockets.connect(
            ws_url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5
        ) as ws:

            # ── Step 1: Send voice configuration ──
            voice_config = {
                "voice_config": {
                    "voiceId": voice["voiceId"],
                    "locale":  voice["locale"],
                    "style":   voice["style"],
                    "rate":    0,       # 0 = normal speed. Range: -50 to +50
                    "pitch":   0,       # 0 = normal pitch. Range: -50 to +50
                    "variation": 1      # slight natural variation in voice
                }
            }
            await ws.send(json.dumps(voice_config))

            # ── Step 2: Send text with end=True to close the context ──
            # This tells Murf: "this is the complete text, start generating"
            text_payload = {
                "text": text,
                "end": True   # Important: tells Murf this is the final text chunk
            }
            await ws.send(json.dumps(text_payload))

            # ── Step 3: Receive audio chunks until "final" signal ──
            while True:
                try:
                    raw_message = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    message = json.loads(raw_message)
                except asyncio.TimeoutError:
                    print("⏱️ Murf websocket timeout. Assuming end of audio.")
                    break
                except json.JSONDecodeError:
                    continue

                if "audio" in message:
                    audio_bytes = base64.b64decode(message["audio"])
                    audio_chunks.append(audio_bytes)

                elif "error" in message:
                    print(f"❌ Murf API Error: {message['error']}")
                    return b""

                # "final": True means all audio has been sent
                if message.get("final"):
                    break

    except websockets.exceptions.ConnectionClosedError as e:
        print(f"❌ Murf WebSocket closed unexpectedly: {e}")
        return b""
    except Exception as e:
        print(f"❌ Murf TTS error: {e}")
        return b""

    if not audio_chunks:
        print("❌ Murf returned no audio chunks")
        return b""

    # ── Step 4: Combine all audio chunks into one blob ──
    combined_audio = b"".join(audio_chunks)
    
    # ── Step 5: Strip the 44-byte WAV header to get pure 16-bit PCM ──
    if combined_audio.startswith(b"RIFF"):
        pcm_bytes = combined_audio[44:]
    else:
        pcm_bytes = combined_audio
        
    print(f"✅ Audio ready for Exotel: {len(pcm_bytes)} bytes (WAV header stripped, pure PCM)")
    return pcm_bytes


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
            "Namaste! Main Binjwa IT Solutions se bol raha hoon. Aapki kya madad kar sakta hoon?",
            lang_code="hi"
        )
        if pcm:
            print(f"✅ Hindi test passed — {len(pcm)} PCM bytes")
        else:
            print("❌ Hindi test FAILED")

        # Test 2: English
        print("\n[Test 2] English voice...")
        pcm = await generate_pcm(
            "Hello! This is Binjwa IT Solutions. How can I help you today?",
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