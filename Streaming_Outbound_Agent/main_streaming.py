"""
main_streaming.py — WebSocket Streaming Voice Agent
=====================================================
PURANA flow (main.py):  Record → upload → download → STT → LLM → TTS  = 2-3 sec
NAYA flow (yeh file):   Live audio WebSocket pe → khud VAD → turant pipeline = 0.8-1.2 sec

✅ VERIFIED against official Vobiz docs:
   - docs.vobiz.ai/xml/stream            → <Stream> element + attributes
   - docs.vobiz.ai/integrations/websockets → WS event protocol + audio format
   - Reference repo: github.com/vobiz-ai/Vobiz-Python-Voice-API-Example

Key facts from docs:
   - Incoming: start, media (har 20ms), playedStream, stop
   - Outgoing: playAudio, clearAudio (barge-in), checkpoint
   - Audio: mulaw 8kHz, 160-byte frames = 20ms (bade chunks = jittery audio)

Run: uvicorn main_streaming:app --host 0.0.0.0 --port 8000
"""

import os
import json
import uuid
import base64
import asyncio
import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response as FastAPIResponse
from dotenv import load_dotenv

from llm import get_base_prompt, generate_llm_response, summarize_call
from stt import transcribe_audio
from tts import stream_tts_audio  # Murf WS streaming — already project mein hai
from crm_webhook import push_to_crm
from calendar_cache import warm_cache
from vad import SilenceDetector, mulaw_to_pcm16, pcm16_to_mulaw, pcm16_to_wav

load_dotenv()

app = FastAPI(title="Streaming Voice Agent v2")

VOBIZ_AUTH_ID = os.getenv("IVR_VOBIZ_AUTH_ID")
VOBIZ_AUTH_TOKEN = os.getenv("IVR_VOBIZ_AUTH_TOKEN")
VOBIZ_PHONE = os.getenv("IVR_VOBIZ_PHONE_NUMBER")
BASE_URL = os.getenv("IVR_BASE_URL", "https://your-ngrok.com")
if not BASE_URL.startswith("http"):
    BASE_URL = "https://" + BASE_URL
WS_BASE = BASE_URL.replace("https://", "wss://").replace("http://", "ws://")

call_sessions = {}


@app.on_event("startup")
async def startup():
    warm_cache()  # Calendar cache pehle se bhar do


# ═════════════════════════════════════════════════
# 1. CALL TRIGGER — same as before
# ═════════════════════════════════════════════════
@app.post("/api/trigger_ai_call")
async def trigger_ai_call(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = dict(await request.form())

    phone = str(data.get("phone_number", data.get("phone", ""))).strip()
    name = data.get("customer_name", data.get("name", "Customer"))
    lang = data.get("lang", "hi")

    if not phone:
        return FastAPIResponse(content='{"status":"error","message":"Missing phone"}', status_code=400)

    if len(phone) == 10 and phone.isdigit():
        phone = f"+91{phone}"
    elif len(phone) == 12 and phone.startswith("91"):
        phone = f"+{phone}"

    session_id = uuid.uuid4().hex
    greeting = f"नमस्ते {name}! मैं Binjwa IT Solutions से बात कर रही हूँ। आप कैसे हैं?"
    if lang == "en":
        greeting = f"Hello {name}! I am calling from Binjwa IT Solutions. How are you doing today?"

    call_sessions[session_id] = {
        "name": name, "phone": phone, "lang": lang, "call_uuid": "unknown",
        "history": [
            {"role": "system", "content": get_base_prompt(lang)},
            {"role": "assistant", "content": greeting},
        ],
        "greeting": greeting,
    }

    url = f"https://api.vobiz.ai/api/v1/Account/{VOBIZ_AUTH_ID}/Call/"
    payload = {
        "from": VOBIZ_PHONE,
        "to": phone,
        "answer_url": f"{BASE_URL}/vobiz_answer/{session_id}",
        "answer_method": "GET",
        "hangup_url": f"{BASE_URL}/call_status/{session_id}",
        "hangup_method": "POST",
    }
    headers = {"X-Auth-ID": VOBIZ_AUTH_ID, "X-Auth-Token": VOBIZ_AUTH_TOKEN,
               "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers)
        rdata = resp.json()
        call_sessions[session_id]["call_uuid"] = rdata.get("call_uuid", rdata.get("CallUUID", "unknown"))

    push_to_crm({"event_type": "call_initiated", "call_uuid": call_sessions[session_id]["call_uuid"],
                 "customer_phone": phone, "customer_name": name, "agent_type": "streaming_ai"})

    return {"status": "success", "message": f"Streaming AI call triggered to {name}"}


# ═════════════════════════════════════════════════
# 2. ANSWER XML — <Stream> instead of <Play>/<Record>
# ═════════════════════════════════════════════════
@app.api_route("/vobiz_answer/{session_id}", methods=["GET", "POST"])
async def vobiz_answer(session_id: str):
    """
    ✅ CONFIRMED from docs.vobiz.ai/xml/stream:
       - bidirectional="true"  → do-taraफa audio
       - keepCallAlive="true"  → stream ke dauran call zinda rehti hai
       - contentType="audio/x-mulaw;rate=8000" → valid codec option
       - audioTrack default "inbound" — bidirectional ke saath yahi chahiye
    """
    if session_id not in call_sessions:
        return FastAPIResponse(content="<Response><Hangup/></Response>", media_type="application/xml")

    ws_url = f"{WS_BASE}/ws/{session_id}"
    status_cb = f"{BASE_URL}/stream_status/{session_id}"

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Stream bidirectional="true" keepCallAlive="true" contentType="audio/x-mulaw;rate=8000" statusCallbackUrl="{status_cb}">{ws_url}</Stream>
</Response>"""
    return FastAPIResponse(content=xml, media_type="application/xml")


@app.api_route("/stream_status/{session_id}", methods=["GET", "POST"])
async def stream_status(session_id: str, request: Request):
    """Vobiz StartStream/PlayedStream/StopStream HTTP callbacks — logging ke liye."""
    try:
        form = dict(await request.form())
        print(f"📡 Stream event: {form.get('Event')} | Call: {form.get('CallUUID', '')[:8]}")
    except Exception:
        pass
    return FastAPIResponse(content="OK", status_code=200)


# ═════════════════════════════════════════════════
# 3. THE CORE — WebSocket audio handler
# ═════════════════════════════════════════════════
@app.websocket("/ws/{session_id}")
async def ws_audio(ws: WebSocket, session_id: str):
    await ws.accept()
    session = call_sessions.get(session_id)
    if not session:
        await ws.close()
        return

    lang = session["lang"]
    vad = SilenceDetector(sample_rate=8000, silence_duration_ms=600)
    stream_id = None
    agent_speaking = asyncio.Event()   # barge-in ke liye
    processing = False

    print(f"🔌 WebSocket connected: {session['name']} ({session['phone']})")

    # ── Vobiz ko audio bhejne ka helper ──
    # ✅ CONFIRMED (docs.vobiz.ai/xml/stream + /integrations/websockets):
    #    playAudio event, mulaw 8kHz, 160-byte chunks (= 20ms telephony framing)
    #    "Larger chunks cause jitter or robotic audio" — Vobiz docs
    MULAW_FRAME = 160  # 160 bytes mulaw @ 8kHz = exactly 20ms

    async def send_audio_to_caller(pcm16_chunk: bytes):
        """PCM16 → mulaw → 160-byte frames → base64 → Vobiz playAudio events."""
        mulaw = pcm16_to_mulaw(pcm16_chunk)
        for i in range(0, len(mulaw), MULAW_FRAME):
            frame = mulaw[i:i + MULAW_FRAME]
            await ws.send_text(json.dumps({
                "event": "playAudio",
                "media": {
                    "contentType": "audio/x-mulaw",
                    "sampleRate": 8000,
                    "payload": base64.b64encode(frame).decode(),
                }
            }))

    async def speak(text: str, checkpoint_name: str = None):
        """Murf TTS stream → live chunks caller ko. Barge-in supported.
        ✅ CONFIRMED: clearAudio event — docs: 'Crucial for barge-in (interruption)'
        ✅ CONFIRMED: checkpoint event — playback complete hone pe playedStream milta hai"""
        agent_speaking.set()
        try:
            async for wav_chunk in stream_tts_audio(text, lang):
                # Customer beech mein bol pada? → chup ho jao (barge-in)
                if vad.is_user_speaking():
                    print("✋ Barge-in — agent stopped mid-sentence")
                    await ws.send_text(json.dumps({"event": "clearAudio"}))
                    break
                # Murf WAV header pehle chunk mein hota hai — 44 bytes skip
                pcm = wav_chunk[44:] if wav_chunk[:4] == b"RIFF" else wav_chunk
                if pcm:
                    await send_audio_to_caller(pcm)
            else:
                # Poora audio queue hua — checkpoint lagao taaki pata chale kab play complete hua
                if checkpoint_name:
                    await ws.send_text(json.dumps({
                        "event": "checkpoint", "name": checkpoint_name
                    }))
        finally:
            agent_speaking.clear()

    async def process_turn(utterance_pcm16: bytes):
        """Customer ka turn complete → STT → LLM → TTS. Filler turant bolo."""
        nonlocal processing
        processing = True
        try:
            # 1. Filler turant — customer ko instant response feel ho
            asyncio.create_task(speak("हम्म..." if lang == "hi" else "Hmm..."))

            # 2. STT
            wav_bytes = pcm16_to_wav(utterance_pcm16)
            user_text = await asyncio.to_thread(transcribe_audio, wav_bytes)
            print(f"👤 Customer: {user_text}")

            if not user_text or len(user_text.strip()) < 2:
                return

            session["history"].append({"role": "user", "content": user_text})
            push_to_crm({"event_type": "user_speech", "call_uuid": session["call_uuid"],
                         "customer_name": session["name"], "text": user_text})

            # 3. LLM
            reply = await asyncio.to_thread(generate_llm_response, session["history"], lang)

            # [END_CALL] marker — TTS ko jaane se PEHLE strip karo (warna bol dega!)
            end_call = "[END_CALL]" in reply
            reply = reply.replace("[END_CALL]", "").strip()

            session["history"].append({"role": "assistant", "content": reply})
            print(f"🤖 Agent: {reply}" + (" [call ending]" if end_call else ""))

            push_to_crm({"event_type": "agent_speech", "call_uuid": session["call_uuid"],
                         "customer_name": session["name"], "text": reply})

            # 4. TTS — live stream back
            booking_done = end_call or "सफलतापूर्वक बुक" in reply or "successfully booked" in reply
            if booking_done:
                # checkpoint lagao — poora message play hone pe Vobiz 'playedStream'
                # event bhejta hai, wahan cleanly hangup karenge (receive loop mein)
                session["hangup_after_checkpoint"] = "final_message"
                await speak(reply, checkpoint_name="final_message")
            else:
                await speak(reply)
        finally:
            processing = False

    # ── Main receive loop ──
    try:
        # Greeting turant bolo jab stream start ho
        greeted = False

        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            event = msg.get("event")

            if event == "start":
                # ✅ CONFIRMED: start event stream ke beginning mein ek baar aata hai
                stream_id = msg.get("start", {}).get("streamId", msg.get("streamId"))
                if not greeted:
                    greeted = True
                    asyncio.create_task(speak(session["greeting"]))
                    push_to_crm({"event_type": "call_picked_up", "call_uuid": session["call_uuid"],
                                 "customer_phone": session["phone"], "customer_name": session["name"],
                                 "agent_type": "streaming_ai"})

            elif event == "media":
                # ✅ CONFIRMED: media event har 20ms aata hai jab caller bolta hai
                payload_b64 = msg.get("media", {}).get("payload", "")
                if not payload_b64:
                    continue
                mulaw = base64.b64decode(payload_b64)
                pcm16 = mulaw_to_pcm16(mulaw)

                # Agent bol raha ho toh bhi VAD chalao (barge-in detection ke liye)
                turn_done = vad.feed(pcm16)

                if turn_done and not processing:
                    utterance = vad.get_and_reset_buffer()
                    asyncio.create_task(process_turn(utterance))

            elif event == "playedStream":
                # ✅ CONFIRMED: checkpoint tak ka audio play complete hua
                name = msg.get("name", "")
                if session.get("hangup_after_checkpoint") == name:
                    print(f"✅ Final message played — hanging up cleanly")
                    await ws.close()
                    break

            elif event == "stop":
                print("🛑 Stream stopped by Vobiz")
                break

    except WebSocketDisconnect:
        print(f"📴 WebSocket disconnected: {session['name']}")
    finally:
        # Call summary
        history = session.get("history", [])
        if history:
            summary = await asyncio.to_thread(summarize_call, history)
            transcript = "\n".join(
                f"{'Customer' if m['role']=='user' else 'Agent'}: {m['content']}"
                for m in history if m["role"] != "system"
            )
            push_to_crm({"event_type": "call_summary", "call_uuid": session["call_uuid"],
                         "summary": summary, "transcript": transcript})


# ═════════════════════════════════════════════════
# 4. Hangup callback — same as before
# ═════════════════════════════════════════════════
@app.api_route("/call_status/{session_id}", methods=["GET", "POST"])
async def call_status(session_id: str, request: Request):
    session = call_sessions.get(session_id)
    if session:
        push_to_crm({"event_type": "call_disconnected", "call_uuid": session["call_uuid"],
                     "customer_phone": session["phone"], "customer_name": session["name"]})
    return FastAPIResponse(content="OK", status_code=200)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main_streaming:app", host="0.0.0.0", port=8000, reload=True)