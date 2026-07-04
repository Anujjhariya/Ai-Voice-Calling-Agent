"""
agent_outbound.py
=================
AI Agent Outbound Calling System

Handles agent-initiated calls where the agent talks to customers using:
  - AI responses via LLM (Groq Llama)
  - Emotional voices via Murf.ai
  - Speech recognition via Groq Whisper
  - Calendar integration for booking meetings

WebSocket Protocol (Agent <-> Customer):
  Agent: Greeting → Listen → Process → Respond → Repeat → Close

This is separate from the IVR system which handles customer-initiated calls.
"""

import os
import json
import asyncio
import re
import urllib.parse
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request
from fastapi.responses import Response as FastAPIResponse
from groq import Groq
from dotenv import load_dotenv

from llm import get_response, get_base_prompt, generate_llm_completion_with_fallback
from tts import generate_pcm
from stt import transcribe_audio
from calendar_api import book_meeting

load_dotenv()

router = APIRouter(prefix="/agent", tags=["Agent Outbound Calling"])

# ─────────────────────────────────────────────────────────────
# IN-MEMORY STATE — Track agent call sessions
# ─────────────────────────────────────────────────────────────

agent_call_sessions = {}  # { call_uuid: { state, history, emotion, lang, customer_name, ... } }

class AgentCallSession:
    """Represents a single agent outbound call"""
    def __init__(self, call_uuid: str, customer_name: str = "Customer", 
                 emotion: str = "happy", lang: str = "en"):
        self.call_uuid = call_uuid
        self.customer_name = customer_name
        self.emotion = emotion
        self.lang = lang
        self.state = "greeting"  # greeting → listening → processing → responding → listening → ...
        self.conversation_history = []
        self.started_at = datetime.now()
        self.last_activity = datetime.now()
        
    def add_message(self, role: str, content: str):
        """Add to conversation history"""
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        self.last_activity = datetime.now()
        
    def get_messages_for_llm(self):
        """Format conversation history for LLM"""
        return [
            {"role": m["role"], "content": m["content"]}
            for m in self.conversation_history
        ]

# ─────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────

def xml_resp(content: str) -> FastAPIResponse:
    """Helper to return clean XML response to Vobiz."""
    xml_body = "".join(content.splitlines()).strip()
    xml_body = re.sub(r'>\s+<', '><', xml_body)
    if not xml_body.startswith("<?xml"):
        xml_body = f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_body}'
    print(f"\n🤖 [AGENT XML RESPONSE]:\n{xml_body}\n")
    return FastAPIResponse(content=xml_body, media_type="text/xml")

def say_with_emotion(text: str, emotion: str = "happy", lang: str = "en") -> str:
    """
    Wrap text for Vobiz with emotional voice.
    Returns <Speak> tag or <Play> tag with TTS audio.
    """
    # Map emotions to voice codes
    emotion_map = {
        "happy": f"{lang}_happy",
        "professional": f"{lang}_professional",
        "excited": f"{lang}_male_excited" if lang == "en" else f"{lang}_excited",
        "warm": lang,  # Use default conversational
        "conversational": lang,
    }
    
    voice_code = emotion_map.get(emotion, lang)
    
    # For now, use Polly as fallback (we can make dynamic TTS calls)
    if lang == "en":
        return f'<Speak language="en-IN" voice="Polly.Aditi">{text}</Speak>'
    elif lang == "hi":
        return f'<Speak language="hi-IN" voice="Polly.Aditi">{text}</Speak>'
    else:
        return f'<Speak>{text}</Speak>'

# ─────────────────────────────────────────────────────────────
# AGENT CONVERSATION FLOW
# ─────────────────────────────────────────────────────────────

async def get_agent_response(session: AgentCallSession, user_input: str = "") -> str:
    """
    Get AI agent response using LLM.
    """
    # The user_input is already added to session history before this function is called.
    
    # Build prompt with conversation history
    base_prompt = get_base_prompt(session.lang)
    
    messages = [
        {"role": "system", "content": base_prompt}
    ] + session.get_messages_for_llm()
    
    # Get response from LLM using the unified fallback function
    response = await asyncio.to_thread(generate_llm_completion_with_fallback, messages)
    
    session.add_message("assistant", response)
    print(f"🤖 [Agent] ({session.emotion}): {response}")
    
    return response

# ─────────────────────────────────────────────────────────────
# VOBIZ ENDPOINT — Outbound call entry point
# ─────────────────────────────────────────────────────────────

@router.get("/outbound_call")
@router.post("/outbound_call")
async def outbound_call_start(request: Request):
    """
    Entry point when agent initiates call to customer.
    Called by Vobiz when customer picks up.
    
    Query params:
        - name: Customer name
        - emotion: Agent emotion (happy, professional, excited, warm, conversational)
        - lang: Language code (en, hi, mr, gu, pa)
    """
    # Extract parameters
    name = request.query_params.get("name", "Customer")
    emotion = request.query_params.get("emotion", "happy").lower()
    lang = request.query_params.get("lang", "en").lower()
    
    # Get call info from Vobiz
    data = dict(request.query_params)
    if request.method == "POST":
        try:
            data.update(await request.json())
        except:
            pass
    
    call_uuid = data.get("CallUUID", data.get("call_uuid", ""))
    from_phone = data.get("From", data.get("from", ""))
    to_phone = data.get("To", data.get("to", ""))
    direction = data.get("Direction", data.get("direction", "outbound")).lower()
    
    # Create session
    session = AgentCallSession(call_uuid, name, emotion, lang)
    agent_call_sessions[call_uuid] = session
    
    print(f"\n{'='*60}")
    print(f"🤖 AGENT OUTBOUND CALL STARTED")
    print(f"{'='*60}")
    print(f"📞 Call UUID: {call_uuid}")
    print(f"👤 Customer: {name}")
    print(f"🎭 Emotion: {emotion.upper()}")
    print(f"🗣️  Language: {lang.upper()}")
    print(f"{'='*60}\n")
    
    # Generate greeting with emotion
    greeting = f"Hello {name}! This is an AI assistant from Binjwa IT Solutions. How are you doing today?"
    if lang == "hi":
        greeting = f"नमस्ते {name}! मैं Binjwa IT Solutions की AI assistant हूँ। आप कैसे हैं?"
    
    session.add_message("assistant", greeting)
    
    # Create Vobiz XML response: play greeting first, then gather customer response
    base_url = os.getenv("IVR_BASE_URL")
    encoded_name = urllib.parse.quote(name)
    
    action_url = f"{base_url}/agent/handle_response?call_uuid={call_uuid}&amp;name={encoded_name}&amp;emotion={emotion}&amp;lang={lang}"
    
    # Correct Vobiz format: Speak, Pause for silence, then Gather
    xml = f"""
    <Response>
        {say_with_emotion(greeting, emotion, lang)}
        <Record action="{action_url}" method="POST" maxLength="60" timeout="5" playBeep="true" />
        <Redirect method="POST">{action_url}</Redirect>
    </Response>
    """
    
    return xml_resp(xml)


# ─────────────────────────────────────────────────────────────
# HANDLE CUSTOMER RESPONSE
# ─────────────────────────────────────────────────────────────

@router.post("/handle_response")
async def handle_customer_response(request: Request):
    """
    Process customer's spoken response.
    
    Vobiz sends:
        - SpeechResult or RecordingUrl with customer's speech
        - DTMF digits (if any)
    """
    data = dict(request.query_params)
    try:
        form_data = await request.form()
        data.update({k: v for k, v in form_data.items()})
    except:
        pass
    
    try:
        json_data = await request.json()
        data.update(json_data)
    except:
        pass
    
    call_uuid = data.get("call_uuid", data.get("CallUUID", ""))
    name = data.get("name", "Customer")
    emotion = data.get("emotion", "happy").lower()
    lang = data.get("lang", "en").lower()
    
    print(f"\n📞 [Recording Received] CallUUID: {call_uuid}")
    print(f"📊 Available fields: {list(data.keys())}")
    
    # Get or create session
    if call_uuid not in agent_call_sessions:
        session = AgentCallSession(call_uuid, name, emotion, lang)
        agent_call_sessions[call_uuid] = session
    else:
        session = agent_call_sessions[call_uuid]
    
    # Extract customer's speech - try multiple field names
    customer_speech = (
        data.get("SpeechResult") or
        data.get("speech_result") or
        data.get("Speech") or
        ""
    ).strip()
    
    recording_url = (
        data.get("RecordingUrl") or
        data.get("RecordFile") or
        data.get("RecordUrl") or
        data.get("recording_url") or
        ""
    )
    
    print(f"🎤 Direct speech: '{customer_speech}'")
    print(f"📁 Recording URL: {recording_url[:50] if recording_url else 'None'}...")
    
    # If no direct speech, try to transcribe recording
    if not customer_speech and recording_url:
        try:
            print(f"⏳ Downloading recording from URL...")
            import tempfile
            import requests
            import os
            
            def download_and_transcribe(url, lang_code):
                try:
                    auth_id = os.getenv("VOBIZ_AUTH_ID") or os.getenv("IVR_VOBIZ_AUTH_ID")
                    auth_token = os.getenv("VOBIZ_AUTH_TOKEN") or os.getenv("IVR_VOBIZ_AUTH_TOKEN")
                    headers = {}
                    auth_tuple = None
                    if auth_id and auth_token:
                        headers = {"X-Auth-ID": auth_id, "X-Auth-Token": auth_token}
                        auth_tuple = (auth_id, auth_token)
                        
                    res = requests.get(url, headers=headers, auth=auth_tuple, timeout=10)
                    res.raise_for_status()
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                        tmp.write(res.content)
                        tmp_path = tmp.name
                    try:
                        return transcribe_audio(tmp_path, lang_code)
                    finally:
                        try:
                            os.remove(tmp_path)
                        except:
                            pass
                except Exception as e:
                    print(f"❌ Failed to download/transcribe: {e}")
                    return "[Could not transcribe audio]"

            customer_speech = await asyncio.to_thread(
                lambda: download_and_transcribe(recording_url, lang)
            )
            print(f"✅ Transcribed: '{customer_speech}'")
        except Exception as e:
            print(f"❌ Failed to transcribe: {e}")
            customer_speech = "[Could not transcribe audio]"
    
    if not customer_speech or customer_speech.startswith("["):
        # No valid speech detected
        print(f"⚠️ No speech detected from customer")
        session.add_message("user", "[silent/no response]")
        
        no_response_msg = "I didn't catch that. Could you please repeat?"
        if lang == "hi":
            no_response_msg = "मुझे ये समझ नहीं आया। कृपया दोबारा बताइए।"
        
        session.add_message("assistant", no_response_msg)
        
        base_url = os.getenv("IVR_BASE_URL")
        encoded_name = urllib.parse.quote(name)
        action_url = f"{base_url}/agent/handle_response?call_uuid={call_uuid}&amp;name={encoded_name}&amp;emotion={emotion}&amp;lang={lang}"
        
        xml = f"""
        <Response>
            {say_with_emotion(no_response_msg, emotion, lang)}
            <Record action="{action_url}" method="POST" maxLength="60" timeout="5" playBeep="true" />
            <Redirect method="POST">{action_url}</Redirect>
        </Response>
        """
        
        return xml_resp(xml)
    
    # Check if customer wants to end call
    end_phrases = ["bye", "goodbye", "no thanks", "stop", "quit", "alvida", "bye bye", "धन्यवाद"]
    if any(phrase in customer_speech.lower() for phrase in end_phrases):
        print(f"👤 [Customer] Wants to end call: {customer_speech}")
        closing = "Thank you for your time! Have a great day!"
        if lang == "hi":
            closing = "आपका समय देने के लिए धन्यवाद! आपका दिन शुभ हो!"
        
        session.add_message("assistant", closing)
        
        xml = f"""
        <Response>
            {say_with_emotion(closing, emotion, lang)}
            <Hangup/>
        </Response>
        """
        return xml_resp(xml)
    
    print(f"👤 [Customer] ({lang}): {customer_speech}")
    session.add_message("user", customer_speech)
    
    # Check if customer wants to schedule a meeting
    booking_keywords = ["meeting", "schedule", "appointment", "book", "time", "when", "मीटिंग", "समय", "कब", "बुक"]
    wants_booking = any(kw in customer_speech.lower() for kw in booking_keywords)
    
    if wants_booking:
        # Ask for meeting time
        booking_ask = "Sure! What time works best for you?"
        if lang == "hi":
            booking_ask = "ठीक है! आपको कौन सा समय सुविधाजनक है?"
        
        session.add_message("assistant", booking_ask)
        
        base_url = os.getenv("IVR_BASE_URL")
        encoded_name = urllib.parse.quote(name)
        action_url = f"{base_url}/agent/process_booking?call_uuid={call_uuid}&amp;name={encoded_name}&amp;emotion={emotion}&amp;lang={lang}"
        
        xml = f"""
        <Response>
            {say_with_emotion(booking_ask, emotion, lang)}
            <Record action="{action_url}" method="POST" maxLength="60" timeout="5" playBeep="true" />
            <Redirect method="POST">{action_url}</Redirect>
        </Response>
        """
        return xml_resp(xml)
    
    # Get AI response to customer's message
    agent_response = await get_agent_response(session, customer_speech)
    
    # Send agent response and record next customer input
    base_url = os.getenv("IVR_BASE_URL")
    encoded_name = urllib.parse.quote(name)
    action_url = f"{base_url}/agent/handle_response?call_uuid={call_uuid}&amp;name={encoded_name}&amp;emotion={emotion}&amp;lang={lang}"
    
    print(f"✅ [Agent] ({emotion}): {agent_response[:80]}...")
    
    xml = f"""
    <Response>
        {say_with_emotion(agent_response, emotion, lang)}
        <Record action="{action_url}" method="POST" maxLength="60" timeout="5" playBeep="true" />
        <Redirect method="POST">{action_url}</Redirect>
    </Response>
    """
    
    return xml_resp(xml)


# ─────────────────────────────────────────────────────────────
# PROCESS BOOKING
# ─────────────────────────────────────────────────────────────

@router.post("/process_booking")
async def process_agent_booking(request: Request):
    """
    Process customer's meeting booking request.
    """
    data = dict(request.query_params)
    try:
        data.update(await request.json())
    except:
        pass
    
    call_uuid = data.get("call_uuid", "")
    name = data.get("name", "Customer")
    emotion = data.get("emotion", "happy").lower()
    lang = data.get("lang", "en").lower()
    
    if call_uuid not in agent_call_sessions:
        session = AgentCallSession(call_uuid, name, emotion, lang)
        agent_call_sessions[call_uuid] = session
    else:
        session = agent_call_sessions[call_uuid]
    
    # Get customer's time preference
    time_preference = data.get("SpeechResult", data.get("speech_result", "")).strip()
    
    if not time_preference:
        time_preference = "[No time specified]"
    
    print(f"📅 [Booking] Customer requested: {time_preference}")
    session.add_message("user", f"I'd like to book at: {time_preference}")
    
    # Confirmation message
    confirmation = f"Perfect! I've noted your preference for {time_preference}. Our team will confirm your meeting soon. Thank you!"
    if lang == "hi":
        confirmation = f"बहुत अच्छा! मैंने {time_preference} के लिए आपकी पसंद दर्ज कर दी है। हमारी टीम जल्दी आपसे संपर्क करेगी। धन्यवाद!"
    
    session.add_message("assistant", confirmation)
    
    # Try to extract and book the meeting
    try:
        await asyncio.to_thread(book_meeting, name, time_preference)
        print(f"✅ Meeting booked for {name}: {time_preference}")
    except Exception as e:
        print(f"⚠️ Booking failed: {e}")
    
    xml = f"""
    <Response>
        {say_with_emotion(confirmation, emotion, lang)}
        <Hangup/>
    </Response>
    """
    
    return xml_resp(xml)


# ─────────────────────────────────────────────────────────────
# CALL ENDED WEBHOOK
# ─────────────────────────────────────────────────────────────

@router.post("/call_ended")
async def on_call_ended(request: Request):
    """
    Called by Vobiz when the call ends (customer hangs up or timeout).
    """
    data = dict(request.query_params)
    try:
        data.update(await request.json())
    except:
        pass
    
    call_uuid = data.get("CallUUID", data.get("call_uuid", ""))
    name = data.get("name", "Customer")
    
    print(f"\n{'='*60}")
    print(f"📞 AGENT CALL ENDED")
    print(f"{'='*60}")
    print(f"📊 Call UUID: {call_uuid}")
    print(f"👤 Customer: {name}")
    
    # Get and log conversation summary
    if call_uuid in agent_call_sessions:
        session = agent_call_sessions[call_uuid]
        duration = (datetime.now() - session.started_at).total_seconds()
        num_exchanges = len(session.conversation_history)
        
        print(f"⏱️  Duration: {duration:.1f}s")
        print(f"💬 Messages: {num_exchanges}")
        print(f"\n📝 Conversation Summary:")
        for msg in session.conversation_history:
            role = "🤖 Agent" if msg["role"] == "assistant" else "👤 Customer"
            print(f"  {role}: {msg['content'][:100]}...")
        
        # Clean up session
        del agent_call_sessions[call_uuid]
    
    print(f"{'='*60}\n")
    
    return {"status": "ok"}


# ─────────────────────────────────────────────────────────────
# UTILITY ENDPOINTS
# ─────────────────────────────────────────────────────────────

@router.get("/sessions")
async def get_active_sessions():
    """Get all active agent call sessions (admin only)."""
    sessions_data = []
    for uuid, session in agent_call_sessions.items():
        duration = (datetime.now() - session.started_at).total_seconds()
        sessions_data.append({
            "call_uuid": uuid,
            "customer_name": session.customer_name,
            "emotion": session.emotion,
            "language": session.lang,
            "state": session.state,
            "duration_seconds": duration,
            "messages": len(session.conversation_history)
        })
    
    return {
        "active_sessions": len(sessions_data),
        "sessions": sessions_data
    }

@router.get("/session/{call_uuid}")
async def get_session_details(call_uuid: str):
    """Get details of a specific agent call session."""
    if call_uuid not in agent_call_sessions:
        return {"error": "Session not found"}, 404
    
    session = agent_call_sessions[call_uuid]
    return {
        "call_uuid": call_uuid,
        "customer_name": session.customer_name,
        "emotion": session.emotion,
        "language": session.lang,
        "state": session.state,
        "started_at": session.started_at.isoformat(),
        "conversation": session.conversation_history
    }
