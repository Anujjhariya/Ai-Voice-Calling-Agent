import os
import uuid
import json
import httpx
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import Response as FastAPIResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from llm import get_base_prompt, generate_llm_response, summarize_call
from stt import transcribe_audio
from tts import generate_audio_file, stream_tts_audio, TTS_PROVIDER
from crm_webhook import push_to_crm

load_dotenv()

app = FastAPI(title="Streaming Outbound Agent")

if not os.path.exists("static"):
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

VOBIZ_AUTH_ID = os.getenv("IVR_VOBIZ_AUTH_ID")
VOBIZ_AUTH_TOKEN = os.getenv("IVR_VOBIZ_AUTH_TOKEN")
VOBIZ_PHONE = os.getenv("IVR_VOBIZ_PHONE_NUMBER")
BASE_URL = os.getenv("IVR_BASE_URL", "https://your-ngrok.com")
if not BASE_URL.startswith("http"):
    BASE_URL = "https://" + BASE_URL

call_sessions = {}

@app.post("/api/trigger_ai_call")
async def trigger_ai_call(request: Request):
    """API for the CRM Dashboard to trigger an AI Agent call."""
    try:
        data = await request.json()
    except Exception:
        try:
            data = dict(await request.form())
        except Exception:
            return FastAPIResponse(content=json.dumps({"status": "error", "message": "Invalid payload format."}), status_code=400)
        
    phone_number = data.get("phone_number", data.get("phoneNumber", data.get("phone", "")))
    name = data.get("customer_name", data.get("customerName", data.get("name", "Customer")))
    lang = data.get("lang", data.get("language", "hi"))
    
    if not phone_number:
        return FastAPIResponse(content=json.dumps({"status": "error", "message": f"Missing phone number."}), status_code=400)
        
    # Format phone number for Vobiz
    phone_number = str(phone_number).strip()
    if len(phone_number) == 10 and phone_number.isdigit():
        phone_number = f"+91{phone_number}"
    elif len(phone_number) == 12 and phone_number.startswith("91"):
        phone_number = f"+{phone_number}"
        
    # Call the core make_call function
    res_data = await make_call(phone=phone_number, name=name, lang=lang)
    
    call_uuid = "unknown"
    if isinstance(res_data, dict):
        call_uuid = res_data.get("call_uuid", res_data.get("CallUUID", "unknown"))
    
    push_to_crm({
        "event_type": "call_initiated",
        "call_uuid": call_uuid,
        "customer_phone": phone_number,
        "ivr_phone": VOBIZ_PHONE,
        "customer_name": name,
        "network": "vobiz",
        "agent_type": "conversational_ai"
    })
    
    return {"status": "success", "message": f"AI Call triggered successfully to {name} ({phone_number})"}

@app.post("/api/make_call")
async def make_call(phone: str, name: str = "Customer", lang: str = "hi"):
    url = f"https://api.vobiz.ai/api/v1/Account/{VOBIZ_AUTH_ID}/Call/"
    session_id = uuid.uuid4().hex
    
    greeting = f"Hello {name}! I am calling from Binjwa IT Solutions. How are you doing today?"
    if lang == "hi":
        greeting = f"नमस्ते {name}! मैं Binjwa IT Solutions से बात कर रही हूँ। आप कैसे हैं?"
        
    ext = "mp3" if TTS_PROVIDER == "elevenlabs" else "wav"
    file_name = f"greet_{session_id}.{ext}"
    file_path = os.path.join("static", file_name)
    await generate_audio_file(greeting, lang, file_path)
    
    call_sessions[session_id] = {
        "name": name,
        "phone": phone,
        "lang": lang,
        "call_uuid": "unknown",
        "history": [
            {"role": "system", "content": get_base_prompt(lang)},
            {"role": "assistant", "content": greeting}
        ],
        "greet_file": file_name,
        "latest_reply": ""
    }
    
    payload = {
        "from": VOBIZ_PHONE,
        "to": phone,
        "answer_url": f"{BASE_URL}/vobiz_answer/{session_id}",
        "answer_method": "GET",
        "hangup_url": f"{BASE_URL}/call_status/{session_id}",
        "hangup_method": "POST",
        "statusCallback": f"{BASE_URL}/call_status/{session_id}",
        "statusCallbackEvent": ["completed"]
    }
    
    headers = {"X-Auth-ID": VOBIZ_AUTH_ID, "X-Auth-Token": VOBIZ_AUTH_TOKEN, "Content-Type": "application/json"}
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers)
        data = resp.json()
        call_uuid = data.get("call_uuid", data.get("CallUUID", "unknown"))
        call_sessions[session_id]["call_uuid"] = call_uuid
        return data

@app.api_route("/vobiz_answer/{session_id}", methods=["GET", "POST"])
async def vobiz_answer(session_id: str):
    session = call_sessions.get(session_id)
    if not session:
        return FastAPIResponse(content="<Response><Hangup/></Response>", media_type="application/xml")
    
    push_to_crm({
        "event_type": "call_picked_up",
        "call_uuid": session["call_uuid"],
        "customer_phone": session["phone"],
        "customer_name": session["name"],
        "ivr_phone": VOBIZ_PHONE,
        "agent_type": "conversational_ai"
    })
    
    file_name = session["greet_file"]
    play_url = f"{BASE_URL}/static/{file_name}"
    action_url = f"{BASE_URL}/agent_response/{session_id}"
    
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>{play_url}</Play>
    <Record action="{action_url}" method="POST" maxLength="15" timeout="1" playBeep="false" />
</Response>"""
    return FastAPIResponse(content=xml, media_type="application/xml")

@app.post("/agent_response/{session_id}")
async def agent_response(session_id: str, request: Request):
    form_data = await request.form()
    record_url = form_data.get("RecordUrl")
    
    session = call_sessions.get(session_id)
    if not session or not record_url:
        return FastAPIResponse(content="<Response><Hangup/></Response>", media_type="application/xml")
    
    lang = session["lang"]
    
    try:
        headers = {"X-Auth-ID": VOBIZ_AUTH_ID, "X-Auth-Token": VOBIZ_AUTH_TOKEN}
        async with httpx.AsyncClient() as client:
            res = await client.get(record_url, headers=headers, auth=(VOBIZ_AUTH_ID, VOBIZ_AUTH_TOKEN), timeout=10.0)
            res.raise_for_status()
            audio_bytes = res.content
    except Exception as e:
        print(f"❌ Failed to download audio: {e}")
        return FastAPIResponse(content="<Response><Hangup/></Response>", media_type="application/xml")
    
    # Fast in-memory STT (No Disk IO)
    user_text = await asyncio.to_thread(transcribe_audio, audio_bytes)
    print(f"👤 Customer: {user_text}")
    
    if not user_text or len(user_text.strip()) < 2:
        print("🔕 (Silence/Noise ignored)")
        action_url = f"{BASE_URL}/agent_response/{session_id}"
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Record action="{action_url}" method="POST" maxLength="15" timeout="1" playBeep="false" />
</Response>"""
        return FastAPIResponse(content=xml, media_type="application/xml")
        
    session["history"].append({"role": "user", "content": user_text})
    
    push_to_crm({
        "event_type": "user_speech",
        "call_uuid": session["call_uuid"],
        "customer_name": session["name"],
        "text": user_text
    })
    
    # Fast LLM processing
    reply_text = await asyncio.to_thread(generate_llm_response, session["history"], lang)
    
    # Check for hangup signal
    should_hangup = False
    if "[END_CALL]" in reply_text:
        should_hangup = True
        reply_text = reply_text.replace("[END_CALL]", "").strip()
        
    session["history"].append({"role": "assistant", "content": reply_text})
    print(f"🤖 Agent: {reply_text}")
    
    push_to_crm({
        "event_type": "agent_speech",
        "call_uuid": session["call_uuid"],
        "customer_name": session["name"],
        "text": reply_text
    })
    
    # Store the reply for the streaming endpoint
    session["latest_reply"] = reply_text
    
    play_url = f"{BASE_URL}/stream_audio/{session_id}"
    action_url = f"{BASE_URL}/agent_response/{session_id}"
    
    if should_hangup or "सफलतापूर्वक बुक हो गई है" in reply_text or "successfully booked" in reply_text:
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>{play_url}</Play>
    <Hangup/>
</Response>"""
    else:
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>{play_url}</Play>
    <Record action="{action_url}" method="POST" maxLength="15" timeout="1" playBeep="false" />
</Response>"""
    
    return FastAPIResponse(content=xml, media_type="application/xml")

@app.get("/stream_audio/{session_id}")
async def stream_audio_endpoint(session_id: str):
    """
    Vobiz hits this endpoint immediately after receiving the <Play> tag.
    We stream the audio bytes directly from the TTS API to Vobiz over HTTP.
    """
    session = call_sessions.get(session_id)
    if not session or not session.get("latest_reply"):
        return FastAPIResponse(content="Error", status_code=404)
        
    text = session["latest_reply"]
    lang = session["lang"]
    
    ext = "mp3" if TTS_PROVIDER == "elevenlabs" else "wav"
    media_type = "audio/mpeg" if ext == "mp3" else "audio/wav"
    
    async def audio_generator():
        async for chunk in stream_tts_audio(text, lang):
            yield chunk

    return StreamingResponse(audio_generator(), media_type=media_type)

@app.api_route("/call_status/{session_id}", methods=["GET", "POST"])
async def call_status(session_id: str, request: Request):
    """Fired by Vobiz when the call disconnects."""
    session = call_sessions.get(session_id)
    if not session:
        return FastAPIResponse(content="OK", status_code=200)
        
    call_uuid = session.get("call_uuid", "unknown")
    phone = session.get("phone", "unknown")
    name = session.get("name", "Customer")
    
    print(f"📴 Call disconnected for {name} ({phone})")
    
    # 1. Fire Disconnected Event
    push_to_crm({
        "event_type": "call_disconnected",
        "call_uuid": call_uuid,
        "customer_phone": phone,
        "customer_name": name,
        "ivr_phone": VOBIZ_PHONE,
        "agent_type": "conversational_ai"
    })
    
    # 2. Fire Summary Event
    history = session.get("history", [])
    if history:
        async def push_summary():
            summary_text = await asyncio.to_thread(summarize_call, history)
            
            transcript_lines = []
            for msg in history:
                if msg["role"] == "system": continue
                role = "Customer" if msg["role"] == "user" else "Agent"
                transcript_lines.append(f"{role}: {msg['content']}")
            transcript = "\n".join(transcript_lines)
            
            push_to_crm({
                "event_type": "call_summary",
                "call_uuid": call_uuid,
                "ivr_phone": VOBIZ_PHONE,
                "summary": summary_text,
                "transcript": transcript
            })
            
        asyncio.create_task(push_summary())
        
    return FastAPIResponse(content="OK", status_code=200)

@app.post("/mock_crm_webhook")
async def mock_crm_webhook(request: Request):
    """A local endpoint to visualize CRM webhooks on the terminal."""
    try:
        data = await request.json()
        print("\n" + "="*50)
        print(f"📥 [MOCK CRM RECEIVED EVENT]: {data.get('event_type')}")
        print("-" * 50)
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print("="*50 + "\n")
    except Exception as e:
        print(f"❌ Mock CRM Webhook Error: {e}")
    return {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
