import os
import json
import base64
import asyncio
import audioop
import tempfile
import wave
import requests
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.responses import JSONResponse, Response as FastAPIResponse
from dotenv import load_dotenv

from llm import get_response
from stt import transcribe_audio
from tts import generate_pcm, generate_pcm_stream
from calendar_api import book_meeting
from ivr import router as ivr_router
from script_manager import router as scripts_router

load_dotenv()

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Allow the React frontend to communicate with this server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For testing purposes
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ivr_router)
app.include_router(scripts_router)

call_history = {}
RECORD_SECONDS    = 15
CHUNK_MS          = 20
CHUNKS_TO_COLLECT = int((RECORD_SECONDS * 1000) / CHUNK_MS)  # 750 chunks
SILENCE_THRESHOLD = 1000  # Increased to prevent static noise from triggering listening
SILENCE_CHUNKS_CUTOFF = 40  # 800ms of silence to ensure user has finished speaking

# ── Pre-cached greeting ─────────────────────────────────────
GREETING_TEXT = "Hello! I am calling from Binjwa IT Solutions. We provide legal consultancy, digital marketing, and web development services. How can I help you today?"
GREETING_AUDIO = None

@app.on_event("startup")
async def preload_greeting():
    global GREETING_AUDIO
    print("⏳ Pre-generating greeting audio...")
    try:
        GREETING_AUDIO = await generate_pcm(GREETING_TEXT)
        print(f"✅ Greeting cached: {len(GREETING_AUDIO)} bytes")
    except Exception as e:
        print(f"❌ Failed to pre-generate greeting: {e}")

def push_to_crm(payload: dict):
    """Push event data to the CRM Webhook in the background."""
    webhook_url = os.getenv("CRM_WEBHOOK_URL")
    webhook_url = os.getenv("CRM_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return
        
    def do_push():
        try:
            import requests
            res = requests.post(webhook_url, json=payload, 
                                headers={"Content-Type": "application/json"},
                                timeout=3)
            print(f"🌐 [CRM Webhook] {payload.get('event_type')}: HTTP {res.status_code}")
        except Exception as e:
            print(f"⚠️ [CRM Webhook] Skipped ({e.__class__.__name__})")
            
    asyncio.create_task(asyncio.to_thread(do_push))

@app.post("/api/trigger_ai_call")
async def trigger_ai_call(request: Request):
    """
    API for the CRM Dashboard to trigger an AI Agent call.
    """
    try:
        data = await request.json()
    except Exception:
        try:
            data = dict(await request.form())
        except Exception:
            return JSONResponse({"status": "error", "message": "Invalid payload format. Must be JSON or Form Data."}, status_code=400)
        
    phone_number = data.get("phone_number", data.get("phoneNumber", data.get("phone", "")))
    name = data.get("customer_name", data.get("customerName", data.get("name", "Customer")))
    
    if not phone_number:
        return JSONResponse({"status": "error", "message": f"Missing phone number. Received data: {data}"}, status_code=400)
        
    base_url = os.getenv("BASE_URL")
    auth_id = os.getenv("VOBIZ_AUTH_ID")
    auth_token = os.getenv("VOBIZ_AUTH_TOKEN")
    vobiz_phone = os.getenv("VOBIZ_PHONE_NUMBER")
    
    # Format phone number for Vobiz
    phone_number = phone_number.strip()
    if len(phone_number) == 10 and phone_number.isdigit():
        phone_number = f"+91{phone_number}"
    elif len(phone_number) == 12 and phone_number.startswith("91"):
        phone_number = f"+{phone_number}"
        
    url = f"https://api.vobiz.ai/api/v1/Account/{auth_id}/Call/"
    encoded_name = name.replace(" ", "%20")
    
    payload = {
        "from": vobiz_phone,
        "to": phone_number,
        "answer_url": f"{base_url}/vobiz_xml?name={encoded_name}",
        "answer_method": "GET"
    }
    
    def make_call():
        res = requests.post(
            url, 
            json=payload, 
            headers={"X-Auth-ID": auth_id, "X-Auth-Token": auth_token, "Content-Type": "application/json"}
        )
        return res

    # Trigger call
    res = await asyncio.to_thread(make_call)
    
    call_uuid = "unknown"
    if res.status_code in [200, 201, 202]:
        try:
            data = res.json()
            call_uuid = data.get("call_uuid", data.get("CallUUID", "unknown"))
        except:
            pass
    
    push_to_crm({
        "event_type": "call_initiated",
        "call_uuid": call_uuid,
        "customer_phone": phone_number,
        "ivr_phone": vobiz_phone,
        "customer_name": name,
        "network": "vobiz",
        "agent_type": "conversational_ai"
    })
    
    return {"status": "success", "message": f"AI Call triggered successfully to {name} ({phone_number})"}

@app.post("/api/trigger_twilio_call")
async def trigger_twilio_call(request: Request):
    """
    API for the CRM Dashboard to trigger an AI Agent call via TWILIO.
    """
    try:
        data = await request.json()
    except Exception:
        try:
            data = dict(await request.form())
        except Exception:
            return JSONResponse({"status": "error", "message": "Invalid payload format."}, status_code=400)
            
    phone_number = data.get("phone_number", data.get("phoneNumber", data.get("phone", "")))
    name = data.get("customer_name", data.get("customerName", data.get("name", "Customer")))
    
    if not phone_number:
        return JSONResponse({"status": "error", "message": "Missing phone number"}, status_code=400)
        
    base_url = os.getenv("BASE_URL")
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    twilio_phone = os.getenv("TWILIO_PHONE_NUMBER")
    
    phone_number = phone_number.strip()
    if len(phone_number) == 10 and phone_number.isdigit():
        phone_number = f"+91{phone_number}"
    elif len(phone_number) == 12 and phone_number.startswith("91"):
        phone_number = f"+{phone_number}"
        
    encoded_name = name.replace(" ", "%20")
    
    def make_call():
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        call = client.calls.create(
            to=phone_number,
            from_=twilio_phone,
            url=f"{base_url}/twilio_xml?name={encoded_name}",
            method="POST"
        )
        return call.sid

    call_sid = await asyncio.to_thread(make_call)
    
    push_to_crm({
        "event_type": "call_initiated",
        "call_uuid": call_sid,
        "customer_phone": phone_number,
        "ivr_phone": twilio_phone,
        "customer_name": name,
        "network": "twilio",
        "agent_type": "conversational_ai"
    })
    
    return {"status": "success", "message": f"Twilio AI Call triggered successfully to {name} ({phone_number})"}

def get_audio_duration(audio_bytes: bytes) -> float:
    # 8000 bytes = 1 second of ULAW audio
    return len(audio_bytes) / 8000.0

async def process_audio(chunks: list) -> str:
    try:
        mulaw_data = b"".join(chunks)
        pcm_data = audioop.ulaw2lin(mulaw_data, 2)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name

        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            wf.writeframes(pcm_data)

        size = os.path.getsize(wav_path)
        print(f"  💾 WAV: {size} bytes")
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, transcribe_audio, wav_path, "hi")
        
        os.remove(wav_path)
        return result

    except Exception as e:
        print(f"❌ Audio: {e}")
        import traceback
        traceback.print_exc()
        return ""

@app.api_route("/twilio_xml", methods=["GET", "POST"])
async def twilio_xml(request: Request):
    """Twilio hits this endpoint when the customer answers the phone."""
    if request.method == "GET":
        body = dict(request.query_params)
    else:
        try:
            body = dict(await request.form())
        except Exception:
            body = {}

    call_sid = body.get("CallSid", "unknown")
    customer_phone = body.get("To", "")
    print(f"📞 Twilio Incoming call answered: {call_sid}")
    
    push_to_crm({
        "event_type": "call_picked_up",
        "call_uuid": call_sid,
        "customer_phone": customer_phone,
        "network": "twilio",
        "agent_type": "conversational_ai"
    })
    
    base_url = os.getenv("BASE_URL")
    ws_url = base_url.replace("https://", "wss://").replace("http://", "ws://") + f"/ws?call_uuid={call_sid}"

    # For Twilio, we MUST return <Connect><Stream> to start the WebSocket
    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}" />
    </Connect>
</Response>"""
    return Response(content=xml_response, media_type="application/xml")

# ── Vobiz hits this when customer picks up ──────────────────
@app.get("/incoming")
@app.post("/incoming")
@app.get("/vobiz_xml")
@app.post("/vobiz_xml")
async def incoming(request: Request):
    if request.method == "GET":
        body = dict(request.query_params)
    else:
        try:
            body = await request.json()
        except Exception:
            body = dict(await request.form())

    call_uuid = body.get("CallUUID", body.get("call_uuid", "unknown"))
    
    # Correctly identify customer and IVR phone based on direction
    direction = body.get("Direction", body.get("direction", "")).lower()
    if direction == "outbound":
        customer_phone = body.get("To", body.get("to", ""))
        ivr_phone = body.get("From", body.get("from", ""))
    else:
        customer_phone = body.get("From", body.get("from", ""))
        ivr_phone = body.get("To", body.get("to", ""))
        
    if not customer_phone:
        customer_phone = body.get("From", body.get("To", "unknown"))
        ivr_phone = "unknown"
        
    BASE_URL  = os.getenv("BASE_URL")
    AUTH_ID    = os.getenv("VOBIZ_AUTH_ID")
    AUTH_TOKEN = os.getenv("VOBIZ_AUTH_TOKEN")

    print(f"📞 Incoming call received: {call_uuid}")
    
    push_to_crm({
        "event_type": "call_picked_up",
        "call_uuid": call_uuid,
        "customer_phone": customer_phone,
        "ivr_phone": ivr_phone,
        "network": "vobiz",
        "agent_type": "conversational_ai"
    })

    # Vobiz often requires an explicit API call to start the stream
    # We'll do this in a background task to keep the response fast
    async def start_vobiz_stream():
        try:
            ws_url = BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + f"/ws?call_uuid={call_uuid}"
            api_url = f"https://api.vobiz.ai/api/v1/Account/{AUTH_ID}/Call/{call_uuid}/Stream/"
            
            payload = {
                "service_url":   ws_url,
                "bidirectional": True,
                "audio_track":   "inbound",
                "content_type":  "audio/x-mulaw;rate=8000"
            }
            
            # Use asyncio.to_thread for the synchronous requests call
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(None, lambda: requests.post(
                api_url,
                headers={
                    "X-Auth-ID":    AUTH_ID,
                    "X-Auth-Token": AUTH_TOKEN,
                    "Content-Type": "application/json"
                },
                json=payload
            ))
            print(f"📡 Vobiz Stream API: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"❌ Failed to start Vobiz stream: {e}")

    asyncio.create_task(start_vobiz_stream())

    # Return valid XML to keep the call alive while streaming
    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Wait length="3600"/>
</Response>"""

    return Response(content=xml_response, media_type="application/xml")


# ── Vobiz WebSocket — JSON frames with base64 audio ─────────
@app.websocket("/ws")
async def voicebot_ws(websocket: WebSocket):
    await websocket.accept()
    call_uuid = websocket.query_params.get("call_uuid", "unknown")
    print(f"✅ Vobiz WebSocket connected | CallUUID: {call_uuid}")
    audio_chunks = []
    is_listening = False
    processing   = False
    chunk_count  = 0
    silence_chunks   = 0
    speech_detected  = False
    stream_sid   = None

    async def begin_listening(duration: float):
        nonlocal is_listening, audio_chunks, chunk_count
        nonlocal silence_chunks, speech_detected, processing
        await asyncio.sleep(duration)
        audio_chunks   = []
        chunk_count    = 0
        silence_chunks = 0
        speech_detected = False
        is_listening   = True
        processing     = False
        print(f"🎙️ Listening...")

    try:
        # We will wait for 'start' (Twilio) or 'connected' (Vobiz) before sending the greeting
        stream_established = False

        while True:
            try:
                # ✅ KEY: Vobiz sends TEXT frames (JSON), not raw bytes
                raw = await websocket.receive_text()
                msg = json.loads(raw)
            except (WebSocketDisconnect, RuntimeError):
                print(f"📴 WebSocket disconnected")
                push_to_crm({
                    "event_type": "call_disconnected",
                    "call_uuid": call_uuid,
                    "ivr_phone": os.getenv("VOBIZ_PHONE_NUMBER"),
                    "agent_type": "conversational_ai"
                })
                break
            except Exception as e:
                print(f"⚠️ Receive error: {e}")
                break

            event = msg.get("event", "")

            if event == "connected":
                print("📡 Stream connected")
                if not stream_established:
                    stream_established = True
                    # Initial prompt can be triggered via logic here if needed
                    asyncio.create_task(begin_listening(0.5))
                continue

            if event == "start":
                stream_sid = msg.get("streamSid", msg.get("start", {}).get("streamSid"))
                print(f"📡 Twilio Stream started: {stream_sid}")
                
                # Twilio ignores the 'connected' Vobiz payload, so we MUST resend it here
                print("📢 Sending pre-cached greeting (Twilio)...")
                stream_established = True  # Ensure it doesn't double trigger later
                if GREETING_AUDIO:
                    await send_audio_payload(websocket, GREETING_AUDIO, stream_sid)
                    duration = get_audio_duration(GREETING_AUDIO)
                else:
                    await say(websocket, GREETING_TEXT, stream_sid)
                    duration = 5.0
                asyncio.create_task(begin_listening(duration + 0.5))
                continue

            if event == "stopped":
                print("🔚 Stream stopped")
                break

            # ── Incoming audio from caller ──────────────────
            if event == "media":
                if not is_listening or processing:
                    continue

                # Decode base64 mulaw audio
                mulaw_data = base64.b64decode(msg["media"]["payload"])

                pcm_for_vad = audioop.ulaw2lin(mulaw_data, 2)
                energy      = audioop.rms(pcm_for_vad, 2)

                audio_chunks.append(mulaw_data)
                chunk_count += 1

                if energy > SILENCE_THRESHOLD:
                    speech_detected = True
                    silence_chunks  = 0
                else:
                    if speech_detected:
                        silence_chunks += 1

                stop_early = speech_detected and silence_chunks > SILENCE_CHUNKS_CUTOFF

                if chunk_count >= CHUNKS_TO_COLLECT or stop_early:
                    is_listening = False
                    processing   = True

                    import time
                    start_stt = time.time()
                    user_text = await process_audio(audio_chunks)
                    
                    # --- STT Hallucination Filter ---
                    bad_words = ["Генпи", "झाल", "झाल झाल", "अ", "म", "न", "स", "ह", "य", "र", "ल", "व", "श"]
                    if user_text.strip() in bad_words or len(user_text.strip()) < 3:
                        user_text = ""
                        
                    stt_time = time.time() - start_stt
                    print(f"👤 User said: {user_text} (STT: {stt_time:.2f}s)")

                    if user_text.strip():
                        start_llm = time.time()
                        history    = call_history.get(call_uuid, [])
                        loop       = asyncio.get_event_loop()
                        reply_text = await loop.run_in_executor(
                            None, get_response, user_text, history
                        )
                        llm_time = time.time() - start_llm
                        print(f"🤖 Bot reply: {reply_text} (LLM: {llm_time:.2f}s)")

                        speak_text = reply_text
                        should_hangup = False
                        if "BOOK_MEETING:" in reply_text:
                            parts      = reply_text.split("BOOK_MEETING:")
                            speak_text = parts[0].strip()
                            tag_parts  = parts[1].strip().split(":", 1)
                            if len(tag_parts) == 2:
                                c_name, c_time = tag_parts
                                await loop.run_in_executor(None, book_meeting, c_name.strip(), c_time.strip())
                                should_hangup = True
                                push_to_crm({
                                    "event_type": "meeting_booked",
                                    "call_uuid": call_uuid,
                                    "ivr_phone": os.getenv("VOBIZ_PHONE_NUMBER"),
                                    "customer_name": c_name.strip(),
                                    "meeting_time": c_time.strip(),
                                    "agent_type": "conversational_ai"
                                })

                        history.append({"role": "user",      "content": user_text})
                        history.append({"role": "assistant", "content": speak_text})

                        call_history[call_uuid] = history[-10:]

                        import time
                        start_say = time.time()
                        total_bytes = await say(websocket, speak_text, stream_sid)
                        elapsed = time.time() - start_say
                        
                        audio_duration = total_bytes / 8000.0
                        # Only wait for the REMAINING time (if any) + small buffer
                        sleep_duration = max(0.1, audio_duration - elapsed + 0.1)
                        
                        print(f"⏱️ Bot is speaking on phone for {audio_duration:.1f}s (Sent in {elapsed:.1f}s)")
                        
                        if should_hangup:
                            print("👋 Meeting booked! Waiting for audio to finish before hanging up...")
                            await asyncio.sleep(sleep_duration + 0.5)
                            break
                        else:
                            print(f"⏳ Waiting {sleep_duration:.1f}s for audio to finish before listening...")
                            asyncio.create_task(begin_listening(sleep_duration))
                    else:
                        print("🔕 No speech detected")
                        asyncio.create_task(begin_listening(0.5))

    except WebSocketDisconnect:
        print(f"📴 Call ended: {call_uuid}")
        
        # --- PUSH SUMMARY TO CRM ---
        history = call_history.get(call_uuid, [])
        if history:
            webhook_url = os.getenv("CRM_WEBHOOK_URL")
            if webhook_url:
                async def push_summary():
                    from llm import summarize_call
                    try:
                        summary_text = await asyncio.to_thread(summarize_call, history)
                        
                        # Build a clean transcript from call history
                        transcript_lines = []
                        for msg in history:
                            role = "Customer" if msg["role"] == "user" else "Agent"
                            transcript_lines.append(f"{role}: {msg['content']}")
                        transcript = "\n".join(transcript_lines)
                        
                        payload = {
                            "event_type": "call_summary",
                            "call_uuid": call_uuid,
                            "ivr_phone": os.getenv("VOBIZ_PHONE_NUMBER"),
                            "summary": summary_text,
                            "transcript": transcript
                        }
                        res = await asyncio.to_thread(requests.post, webhook_url, json=payload, headers={"Content-Type": "application/json"})
                        print(f"🌐 [CRM Webhook] Pushed call_summary: HTTP {res.status_code}")
                    except Exception as e:
                        print(f"❌ [CRM Webhook Error]: {e}")
                asyncio.create_task(push_summary())
        # ---------------------------
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback; traceback.print_exc()


async def say(websocket: WebSocket, text: str, stream_sid: str = None) -> int:
    """
    STREAMING TTS for Vobiz/Twilio.
    Returns total bytes sent.
    """
    total_bytes = 0
    try:
        print(f"📢 Streaming TTS for: {text[:50]}...")
        async for ulaw_chunk in generate_pcm_stream(text):
            await send_audio_payload(websocket, ulaw_chunk, stream_sid)
            total_bytes += len(ulaw_chunk)
        return total_bytes
    except Exception as e:
        print(f"❌ say() error: {e}")
        return total_bytes

async def send_audio_payload(websocket: WebSocket, audio_bytes: bytes, stream_sid: str = None):
    try:
        # Twilio prefers smaller chunks. We'll chunk to 4000 bytes (0.5s of ULAW)
        chunk_size = 4000
        for i in range(0, len(audio_bytes), chunk_size):
            chunk = audio_bytes[i:i+chunk_size]
            
            if stream_sid:
                # Twilio Format
                payload = {
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {
                        "payload": base64.b64encode(chunk).decode("utf-8")
                    }
                }
            else:
                # Vobiz Format
                payload = {
                    "event": "playAudio",
                    "media": {
                        "contentType": "audio/x-mulaw",
                        "sampleRate":  "8000",
                        "payload":     base64.b64encode(chunk).decode("utf-8")
                    }
                }
            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(0.001)  # tiny yield to prevent blocking event loop
    except Exception as e:
        # Don't log "connection closed" errors as they are expected on hangup
        if "close message" not in str(e):
            print(f"❌ send_audio_payload() error: {e}")


@app.post("/hangup")
async def hangup(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = await request.body()
    print(f"📴 Hangup event: {body}")
    return JSONResponse({"status": "ok"})

@app.post("/stream-status")
async def stream_status(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = await request.body()
    print(f"📡 Stream status: {body}")
    return JSONResponse({"status": "ok"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)