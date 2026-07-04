# web_call.py — Browser WebRTC Voice Agent (no phone number needed)
import os
import json
import base64
import asyncio
import tempfile
import wave
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from llm import get_response
from stt import transcribe_audio
from tts_exotel import generate_pcm

load_dotenv()
app = FastAPI()
call_history = {}

# ── Pre-cached greeting ──
GREETING_TEXT = (
    "नमस्ते! मैं Binjwa IT Solutions से बोल रही हूँ। "
    "क्या मैं आपसे software services के बारे में दो मिनट बात कर सकती हूँ?"
)
GREETING_WAV: bytes = b""


@app.on_event("startup")
async def preload_greeting():
    """Generate greeting WAV once at startup."""
    global GREETING_WAV
    print("[*] Pre-generating greeting audio for browser...")
    pcm = await generate_pcm(GREETING_TEXT)
    if pcm:
        GREETING_WAV = pcm_to_wav(pcm)
        print(f"[OK] Greeting cached: {len(GREETING_WAV)} bytes WAV")
    else:
        print("[ERR] Failed to pre-generate greeting")


def pcm_to_wav(pcm_data: bytes, sample_rate: int = 8000) -> bytes:
    """Convert raw 16-bit PCM to WAV bytes (for browser playback)."""
    import io
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return buf.getvalue()


# ── Serve the web UI ──
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index():
    return FileResponse("static/index.html")


# ── Browser WebSocket ──
@app.websocket("/ws/web")
async def web_voicebot(websocket: WebSocket):
    await websocket.accept()
    session_id = id(websocket)
    history = []
    print(f"\n[WEB] Browser call connected (session: {session_id})")

    try:
        # Send greeting immediately
        if GREETING_WAV:
            await websocket.send_text(json.dumps({
                "type": "greeting",
                "text": GREETING_TEXT,
                "audio": base64.b64encode(GREETING_WAV).decode("utf-8")
            }))
            print(f"[OK] Greeting sent to browser")
        
        # Main conversation loop
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)

            if msg.get("type") == "audio":
                # Decode the audio blob from browser
                audio_b64 = msg["data"]
                audio_bytes = base64.b64decode(audio_b64)

                # Save as temp file for Whisper
                with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
                    tmp.write(audio_bytes)
                    tmp_path = tmp.name

                # Transcribe
                print(f"[MIC] Transcribing browser audio ({len(audio_bytes)} bytes)...")
                loop = asyncio.get_event_loop()
                user_text = await loop.run_in_executor(None, transcribe_audio, tmp_path, "hi")
                os.remove(tmp_path)
                
                print(f"[USER] User said: {user_text}")
                
                # Send transcription back to browser
                await websocket.send_text(json.dumps({
                    "type": "transcription",
                    "text": user_text
                }))

                if not user_text.strip():
                    # No speech detected, tell browser to listen again
                    await websocket.send_text(json.dumps({
                        "type": "reply",
                        "text": "",
                        "audio": ""
                    }))
                    continue

                # Get LLM response
                try:
                    reply_text = await loop.run_in_executor(None, get_response, user_text, history)
                except Exception as e:
                    print(f"[ERR] LLM error: {e}")
                    reply_text = "Sorry, kuch technical issue ho gaya."

                # Handle booking tag
                speak_text = reply_text
                if "BOOK_MEETING:" in reply_text:
                    try:
                        from calendar_api import book_meeting
                        parts = reply_text.split("BOOK_MEETING:")
                        speak_text = parts[0].strip()
                        tag = parts[1].strip().split(":", 1)
                        if len(tag) == 2:
                            result = await loop.run_in_executor(None, book_meeting, tag[0].strip(), tag[1].strip())
                            print(f"[CAL] {result}")
                    except Exception as e:
                        print(f"[ERR] Booking error: {e}")

                print(f"[BOT] Bot: {reply_text}")
                history.append({"role": "user", "content": user_text})
                history.append({"role": "assistant", "content": reply_text})
                history = history[-10:]

                # Generate TTS audio
                pcm = await generate_pcm(speak_text)
                wav_b64 = ""
                if pcm:
                    wav = pcm_to_wav(pcm)
                    wav_b64 = base64.b64encode(wav).decode("utf-8")

                # Send reply to browser
                await websocket.send_text(json.dumps({
                    "type": "reply",
                    "text": speak_text,
                    "audio": wav_b64
                }))

    except WebSocketDisconnect:
        print(f"[WEB] Browser call ended (session: {session_id})")
    except Exception as e:
        print(f"[ERR] Browser call error: {e}")
        import traceback; traceback.print_exc()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
