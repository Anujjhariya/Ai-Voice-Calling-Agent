"""
web_agent.py
------------
Real-time browser voice agent via WebSocket + embeddable floating widget.
Pipeline: Browser Mic -> WebSocket -> Groq Whisper STT -> LLM Fallback -> Murf TTS -> Browser Speaker

Embed on any website with a single script tag:
  <script src="https://your-ngrok-url/static/widget.js"></script>

WebSocket message protocol:
  Browser -> Server:
    {"type": "start", "lang": "hi"}       — start session with language
    {"type": "audio", "data": "<base64>"} — audio chunk (webm/opus from MediaRecorder)
    {"type": "stop"}                       — user stopped speaking, process now
    {"type": "clear"}                      — clear conversation history

  Server -> Browser:
    {"type": "status",     "state": "listening|processing|speaking|idle"}
    {"type": "transcript", "text": "..."}  — what user said
    {"type": "reply",      "text": "..."}  — AI text response
    {"type": "audio",      "data": "<b64>", "format": "wav"} — TTS audio to play
    {"type": "error",      "message": "..."} — error message
"""

import os
import json
import base64
import asyncio
import tempfile
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/web-agent", tags=["Web Voice Agent"])

# Per-session conversation history
# Format: { session_id: [ {"role": "user", "content": "..."}, ... ] }
session_histories: dict[str, list] = {}
session_contexts: dict[str, dict] = {}

# ─────────────────────────────────────────────────────────────
# GREETING — Auto-played when widget opens
# ─────────────────────────────────────────────────────────────
GREETING_TEXTS = {
    "hi": "नमस्ते! मैं Binjwa IT Solutions की AI assistant हूँ। हम website development, mobile app development, और digital marketing की services provide करते हैं। आपकी कैसे मदद कर सकती हूँ?",
    "en": "Hello! I'm the AI assistant for Binjwa IT Solutions. We provide website development, mobile app development, and digital marketing services. How can I help you today?",
    "mr": "नमस्कार! मी Binjwa IT Solutions ची AI assistant आहे. आम्ही website development, mobile app development, आणि digital marketing च्या सेवा देतो. मी तुमची कशी मदत करू शकतो?",
    "gu": "નમસ્તે! હું Binjwa IT Solutions ની AI assistant છું. અમે website development, mobile app development અને digital marketing ની services આપીએ છીએ. હું તમારી કેવી રીતે મદદ કરી શકું?",
    "pa": "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ! ਮੈਂ Binjwa IT Solutions ਦੀ AI assistant ਹਾਂ। ਅਸੀਂ website development, mobile app development ਅਤੇ digital marketing ਦੀਆਂ services ਦਿੰਦੇ ਹਾਂ। ਮੈਂ ਤੁਹਾਡੀ ਕਿਵੇਂ ਮਦਦ ਕਰ ਸਕਦੀ ਹਾਂ?"
}

# Cached greeting audios (base64 strings)
greeting_audio_cache: dict[str, str] = {}

async def pregenerate_web_greetings():
    """Pregenerate and cache greeting audios for all languages to make start instant."""
    from tts import generate_wav
    print("[WebAgent] Pre-generating Web Agent greetings with HAPPY emotion...")
    for lang, text in GREETING_TEXTS.items():
        if lang in greeting_audio_cache:
            continue
        try:
            audio_bytes = await generate_wav(text, lang_code=lang, gender="female", emotion="Happy")
            if audio_bytes:
                greeting_audio_cache[lang] = base64.b64encode(audio_bytes).decode("utf-8")
                print(f"[WebAgent] Cached web greeting ({lang}): {len(audio_bytes)} bytes (HAPPY)")
            await asyncio.sleep(1.2)  # Delay to allow previous Murf websocket session to close completely
        except Exception as e:
            print(f"[WebAgent] Failed to pre-generate web greeting ({lang}): {e}")

@router.on_event("startup")
async def startup_event():
    # Start pre-generation in the background so it doesn't block startup
    asyncio.create_task(pregenerate_web_greetings())


# ─────────────────────────────────────────────────────────────
# PAGE ROUTE — Serves the HTML UI
# ─────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def web_agent_page():
    """Serve the web voice agent HTML page."""
    html_path = os.path.join(os.path.dirname(__file__), "static", "web_agent.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


# ─────────────────────────────────────────────────────────────
# AUDIO TRANSCRIPTION — Groq Whisper (supports webm natively)
# ─────────────────────────────────────────────────────────────

def transcribe_webm(audio_data: bytes, language: str = "hi") -> str:
    """
    Transcribe browser audio (webm/opus from MediaRecorder) using Groq Whisper.
    Groq Whisper supports webm natively — no ffmpeg conversion needed.
    """
    import os
    from groq import Groq

    groq_key = os.getenv("IVR_GROQ_API_KEY")
    if not groq_key:
        print("[WebAgent STT] No GROQ key found")
        return ""

    client = Groq(api_key=groq_key)

    # Save to temp file with .webm extension
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_data)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            result = client.audio.transcriptions.create(
                file=(os.path.basename(tmp_path), f.read()),
                model="whisper-large-v3-turbo",
                language=language,
                response_format="text"
            )
        text = result.strip() if isinstance(result, str) else str(result).strip()
        print(f"[WebAgent STT] Transcribed ({language}): {text}")
        return text
    except Exception as e:
        print(f"[WebAgent STT] Error: {e}")
        return ""
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
# WEBSOCKET HANDLER — Main voice agent loop
# ─────────────────────────────────────────────────────────────

@router.websocket("/ws")
async def web_agent_ws(websocket: WebSocket):
    await websocket.accept()

    session_id = str(id(websocket))
    session_histories[session_id] = []
    audio_chunks: list[bytes] = []
    lang = "hi"

    print(f"[WebAgent] New session connected: {session_id}")

    async def send(msg: dict):
        """Helper to send JSON message to browser."""
        await websocket.send_text(json.dumps(msg, ensure_ascii=False))

    async def send_greeting(lang: str = "hi"):
        """Auto-generate and send greeting audio when widget opens."""
        context = session_contexts.get(session_id, {})
        site_title = context.get("title", "Binjwa IT Solutions")
        is_binjwa = not site_title or "binjwa" in site_title.lower() or "localhost" in context.get("url", "").lower() or "127.0.0.1" in context.get("url", "").lower()
        
        greeting_text = ""
        audio_b64 = None

        if is_binjwa:
            greeting_text = GREETING_TEXTS.get(lang, GREETING_TEXTS["hi"])
            audio_b64 = greeting_audio_cache.get(lang)
        else:
            dynamic_greetings = {
                "hi": f"नमस्ते! मैं {site_title} की AI assistant हूँ। मैं आपकी कैसे सहायता कर सकती हूँ?",
                "en": f"Hello! I'm the AI assistant for {site_title}. How can I help you today?",
                "mr": f"नमस्कार! मी {site_title} ची AI assistant आहे. मी आपली काय मदत करू शकते?",
                "gu": f"નમસ્તે! હું {site_title} ની AI assistant છું. હું તમારી શું મદદ કરી શકું?",
                "pa": f"ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ! ਮੈਂ {site_title} ਦੀ AI assistant ਹਾਂ। ਮੈਂ ਤੁਹਾਡੀ ਕੀ ਮਦਦ ਕਰ ਸਕਦੀ ਹਾਂ?"
            }
            greeting_text = dynamic_greetings.get(lang, dynamic_greetings["hi"])

        await send({"type": "status", "state": "speaking"})
        await send({"type": "reply", "text": greeting_text, "is_greeting": True})
        
        if audio_b64:
            # Send immediately from cache!
            await send({"type": "audio", "data": audio_b64, "format": "wav"})
        else:
            try:
                from tts import generate_wav
                audio_bytes = await generate_wav(greeting_text, lang_code=lang, gender="female")
                if audio_bytes:
                    audio_b64_new = base64.b64encode(audio_bytes).decode("utf-8")
                    await send({"type": "audio", "data": audio_b64_new, "format": "wav"})
            except Exception as e:
                print(f"[WebAgent Greeting TTS Error]: {e}")
        # Seed greeting into history so LLM knows what was said
        session_histories[session_id] = [
            {"role": "assistant", "content": greeting_text}
        ]
        await send({"type": "status", "state": "idle"})

    try:
        # Send connected status — greeting will be triggered by browser "open" message
        await send({"type": "status", "state": "idle", "message": "Connected"})

        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type", "")

            # ── Widget opened — auto-play greeting ──────────
            if msg_type == "open":
                lang = msg.get("lang", "hi")
                context = msg.get("context", {})
                if context:
                    session_contexts[session_id] = context
                audio_chunks = []
                print(f"[WebAgent] Widget opened. Sending greeting in lang: {lang} with context: {bool(context)}")
                asyncio.create_task(send_greeting(lang))

            # ── User starts recording ────────────────────────
            elif msg_type == "start":
                lang = msg.get("lang", "hi")
                audio_chunks = []
                print(f"[WebAgent] Recording started. Lang: {lang}")
                await send({"type": "status", "state": "listening"})


            # ── Audio chunk received ─────────────────────────
            elif msg_type == "audio":
                chunk = base64.b64decode(msg["data"])
                audio_chunks.append(chunk)

            # ── User stopped speaking — process pipeline ─────
            elif msg_type == "stop":
                if not audio_chunks:
                    await send({"type": "status", "state": "idle"})
                    continue

                await send({"type": "status", "state": "processing"})

                # Combine all chunks
                audio_data = b"".join(audio_chunks)
                audio_chunks = []

                # 1. STT — Groq Whisper
                try:
                    user_text = await asyncio.to_thread(transcribe_webm, audio_data, lang)
                except Exception as e:
                    print(f"[WebAgent STT Error]: {e}")
                    user_text = ""

                if not user_text.strip():
                    await send({
                        "type": "error",
                        "message": "Could not hear clearly. Please try again."
                    })
                    await send({"type": "status", "state": "idle"})
                    continue

                # Send transcript to browser
                await send({"type": "transcript", "text": user_text})

                # 2. LLM — Groq → Cerebras → Gemini fallback
                history = session_histories.get(session_id, [])
                context = session_contexts.get(session_id, {})
                try:
                    from llm import get_response
                    reply_text = await asyncio.to_thread(get_response, user_text, history, context, lang)
                except Exception as e:
                    print(f"[WebAgent LLM Error]: {e}")
                    reply_text = "माफ करें, कुछ गड़बड़ हुई। कृपया दोबारा कोशिश करें।"

                # Strip BOOK_MEETING tag from spoken text (handle booking silently)
                speak_text = reply_text
                if "BOOK_MEETING:" in reply_text:
                    parts = reply_text.split("BOOK_MEETING:")
                    speak_text = parts[0].strip()
                    # Attempt to book
                    try:
                        tag_parts = parts[1].strip().split(":", 1)
                        if len(tag_parts) == 2:
                            c_name, c_time = tag_parts
                            from calendar_api import book_meeting
                            await asyncio.to_thread(book_meeting, c_name.strip(), c_time.strip())
                            print(f"[WebAgent] Meeting booked: {c_name} at {c_time}")
                    except Exception as e:
                        print(f"[WebAgent] Meeting booking error: {e}")

                # Update conversation history
                history.append({"role": "user",      "content": user_text})
                history.append({"role": "assistant", "content": speak_text})
                session_histories[session_id] = history[-10:]  # Keep last 5 turns

                # Send reply text to browser (for display)
                await send({"type": "reply", "text": speak_text})

                # 3. TTS — Murf → returns WAV bytes
                await send({"type": "status", "state": "speaking"})
                try:
                    from tts import generate_wav
                    audio_bytes = await generate_wav(speak_text, lang_code=lang, gender="female")
                    if audio_bytes:
                        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                        await send({"type": "audio", "data": audio_b64, "format": "wav"})
                    else:
                        print("[WebAgent TTS] Empty audio returned")
                except Exception as e:
                    print(f"[WebAgent TTS Error]: {e}")

                await send({"type": "status", "state": "idle"})

            # ── Clear conversation history ───────────────────
            elif msg_type == "clear":
                session_histories[session_id] = []
                print(f"[WebAgent] History cleared for session: {session_id}")
                await send({"type": "status", "state": "idle", "message": "Conversation cleared."})

    except WebSocketDisconnect:
        print(f"[WebAgent] Session disconnected: {session_id}")
    except Exception as e:
        print(f"[WebAgent] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session_histories.pop(session_id, None)
        session_contexts.pop(session_id, None)
        print(f"[WebAgent] Session cleaned up: {session_id}")
