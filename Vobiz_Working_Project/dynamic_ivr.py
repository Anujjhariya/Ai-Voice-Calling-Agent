"""
dynamic_ivr.py
--------------
A fully dynamic, Node-based IVR Engine for Binjwa IT Solutions.
This reads the JSON Node Tree from MongoDB (via dynamic_script_manager.py)
and dynamically routes the caller through the nodes based on key presses.
Now fully integrated with:
  1. Groq Whisper (STT) for voice recording transcription.
  2. Groq Llama-3.3 (LLM) for timezone-aware Hinglish datetime parsing.
  3. Real-time Google Calendar availability checks to prevent double booking.
  4. Non-blocking CRM webhook event propagation.
"""

import os
import urllib.parse
import json
import base64
import requests
import asyncio
import re
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request
from fastapi.responses import Response as FastAPIResponse, StreamingResponse
from groq import Groq

# Core components inside Vobiz_Working_Project
from dynamic_script_manager import get_flow
from calendar_api import book_meeting
from tts import generate_wav_stream

router = APIRouter(prefix="/ivr", tags=["Dynamic IVR"])

CAMPAIGN_VOICE = "Polly.Aditi"

# ─────────────────────────────────────────────
# CAMPAIGN QUEUE (Async - Sequential calls only)
# ─────────────────────────────────────────────
class CampaignQueue:
    def __init__(self):
        self.leads = []
        self.is_running = False   # True while a call is live on the phone
        self.is_dialing = False   # True only during the Vobiz API call

    def add_leads(self, new_leads):
        self.leads.extend(new_leads)
        if not self.is_running and not self.is_dialing and self.leads:
            asyncio.create_task(self.dial_next())

    async def dial_next(self):
        """Dial the next lead. Only called when previous call has fully ended."""
        if not self.leads:
            self.is_running = False
            self.is_dialing = False
            print("\n[CAMPAIGN QUEUE] All calls finished!\n")
            return

        if self.is_dialing:
            print("[CAMPAIGN QUEUE] Already dialing - skipping duplicate trigger.")
            return

        self.is_running = True
        self.is_dialing = True
        lead = self.leads.pop(0)
        name = lead.get("name", "Customer")
        phone = lead.get("phone", "").strip()
        webhookId = lead.get("webhookId", "")
        actionId = lead.get("actionId", "")
        print(f"\n[CAMPAIGN QUEUE] Dialing {name} at {phone}... ({len(self.leads)} remaining)\n")

        try:
            # We construct the same logic as trigger_single_call here
            if len(phone) == 10 and phone.isdigit():
                phone = f"+91{phone}"
            elif len(phone) == 12 and phone.startswith("91"):
                phone = f"+{phone}"

            base_url = os.getenv("IVR_BASE_URL")
            auth_id = os.getenv("IVR_VOBIZ_AUTH_ID")
            auth_token = os.getenv("IVR_VOBIZ_AUTH_TOKEN")
            vobiz_phone = os.getenv("IVR_VOBIZ_PHONE_NUMBER", "+911171366938")
            
            url = f"https://api.vobiz.ai/api/v1/Account/{auth_id}/Call/"
            encoded_name = urllib.parse.quote(name)
            
            payload = {
                "from": vobiz_phone,
                "to": phone,
                "answer_url": f"{base_url}/ivr/start?webhookId={webhookId}&name={encoded_name}&actionId={actionId}",
                "answer_method": "GET",
                "hangup_url": f"{base_url}/ivr/hangup?webhookId={webhookId}&actionId={actionId}",
                "hangup_method": "POST"
            }
            
            def make_call():
                res = requests.post(url, json=payload, headers={"X-Auth-ID": auth_id, "X-Auth-Token": auth_token, "Content-Type": "application/json"})
                if res.status_code not in [200, 201]:
                    raise Exception(f"{res.status_code} - {res.text}")
                return res

            res = await asyncio.to_thread(make_call)
            self.is_dialing = False
            
            call_uuid = "unknown"
            try:
                call_uuid = res.json().get("call_uuid", "unknown")
            except:
                pass
                
            push_to_crm({
                "actionId": actionId,
            "event_type": "call_initiated",
                "call_uuid": call_uuid,
                "customer_phone": phone,
                "ivr_phone": vobiz_phone,
                "customer_name": name,
                "agent_type": "dynamic_node_ivr"
            }, webhookId)
            
            print(f"[CAMPAIGN] Call to {name} accepted. Waiting for hangup before next call...")
        except Exception as e:
            print(f"[CAMPAIGN] Failed to dial {name} ({phone}): {e}")
            self.is_dialing = False
            # Auto-skip after 3s delay if no hangup will come
            await asyncio.sleep(3)
            if self.leads:
                asyncio.create_task(self.dial_next())
            else:
                self.is_running = False

    def on_call_ended(self):
        """Called by the hangup webhook when a call fully ends."""
        self.is_running = False
        if self.leads:
            asyncio.create_task(self._delayed_next())
        else:
            print("\n[CAMPAIGN QUEUE] All calls finished!\n")

    async def _delayed_next(self):
        await asyncio.sleep(3)  # 3-second buffer for Vobiz to release the channel
        await self.dial_next()

campaign_queue = CampaignQueue()


def xml_resp(content: str) -> FastAPIResponse:
    """Helper to return clean XML response to Vobiz/Twilio."""
    xml_body = "".join(content.splitlines()).strip()
    xml_body = re.sub(r'>\s+<', '><', xml_body)
    if not xml_body.startswith("<?xml"):
        xml_body = f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_body}'
    print(f"\n📡 [DYNAMIC IVR XML RESPONSE]:\n{xml_body}\n")
    return FastAPIResponse(content=xml_body, media_type="text/xml")

def say(text: str, lang: str = "hi") -> str:
    """Wrap text in a Speak tag or use Play tag for native Murf TTS."""
    if lang.lower() == "mr":
        encoded_text = urllib.parse.quote(text)
        base_url = os.getenv("IVR_BASE_URL")
        return f'<Play>{base_url}/ivr/dynamic_tts?lang=mr&amp;text={encoded_text}</Play>'
    elif lang.lower() == "en" or lang.lower() == "en-us":
        return f'<Speak language="en-US" voice="Polly.Joanna">{text}</Speak>'
    else:
        return f'<Speak language="hi-IN" voice="{CAMPAIGN_VOICE}">{text}</Speak>'

def push_to_crm(payload: dict, webhookId: str = ""):
    """Push event data to the CRM Webhook dynamically based on webhookId."""
    crm_base_url = os.getenv("IVR_CRM_BASE_URL", "").strip()
    if not webhookId:
        webhook_url = os.getenv("IVR_CRM_WEBHOOK_URL", "").strip()
    else:
        if crm_base_url.endswith('/'):
            crm_base_url = crm_base_url[:-1]
        webhook_url = f"{crm_base_url}/api/ivr-agent/voice/{webhookId}"

    if not webhook_url:
        return
        
    def do_push():
        try:
            res = requests.post(webhook_url, json=payload, 
                                headers={"Content-Type": "application/json"},
                                timeout=3)
            print(f"🌐 [CRM Webhook] {payload.get('event_type')}: HTTP {res.status_code} ({webhook_url})")
        except Exception as e:
            print(f"⚠️ [CRM Webhook] Skipped ({e.__class__.__name__})")
            
    asyncio.create_task(asyncio.to_thread(do_push))

def push_to_viasocket(payload: dict):
    """Push IVR response data to Viasocket webhook for Google Sheets automation."""
    viasocket_url = os.getenv("IVR_VIASOCKET_WEBHOOK_URL", "").strip()
    if not viasocket_url:
        return
        
    from datetime import datetime, timezone, timedelta
    kolkata_tz = timezone(timedelta(hours=5, minutes=30))
    payload["timestamp"] = datetime.now(kolkata_tz).strftime("%Y-%m-%d %H:%M:%S")
        
    def do_push():
        try:
            res = requests.post(viasocket_url, json=payload, 
                                headers={"Content-Type": "application/json"},
                                timeout=5)
            print(f"📊 [Viasocket] Pushed to Google Sheet: HTTP {res.status_code}")
        except Exception as e:
            print(f"⚠️ [Viasocket] Skipped ({e.__class__.__name__}: {e})")
            
    asyncio.create_task(asyncio.to_thread(do_push))

def normalize_phone(phone: str) -> str:
    """Ensure phone number always starts with '+'."""
    if not phone:
        return phone
    phone = phone.strip()
    if phone and not phone.startswith("+"):
        phone = f"+{phone}"
    return phone

# In-memory dictionary to store running call transcripts
# Format: { call_uuid_or_phone: [ "IVR: hello", "Customer: pressed 1", ... ] }
ivr_call_logs = {}

def log_ivr_step(call_uuid: str, phone: str, speaker: str, text: str):
    """
    Logs a single step in the IVR call transcript.
    Keys on both call_uuid and phone to ensure we can retrieve it even if one is missing.
    """
    if not text or not text.strip():
        return
    entry = f"{speaker}: {text.strip()}"
    print(f"📝 [LOG STEP] {entry} (UUID: {call_uuid}, Phone: {phone})")
    
    # Store by call_uuid if available
    if call_uuid and call_uuid != "unknown" and call_uuid != "":
        if call_uuid not in ivr_call_logs:
            ivr_call_logs[call_uuid] = []
        if not ivr_call_logs[call_uuid] or ivr_call_logs[call_uuid][-1] != entry:
            ivr_call_logs[call_uuid].append(entry)
            
    # Store by phone if available
    if phone:
        phone_clean = normalize_phone(phone)
        if phone_clean:
            if phone_clean not in ivr_call_logs:
                ivr_call_logs[phone_clean] = []
            if not ivr_call_logs[phone_clean] or ivr_call_logs[phone_clean][-1] != entry:
                ivr_call_logs[phone_clean].append(entry)

def get_ivr_transcript(call_uuid: str, phone: str) -> str:
    """
    Retrieves the compiled transcript for a call using call_uuid or phone number.
    """
    steps = []
    if call_uuid and call_uuid in ivr_call_logs:
        steps = ivr_call_logs[call_uuid]
    elif phone:
        phone_clean = normalize_phone(phone)
        if phone_clean and phone_clean in ivr_call_logs:
            steps = ivr_call_logs[phone_clean]
            
    if not steps:
        return "No transcript recorded."
        
    return "\n".join(steps)

def summarize_ivr_call(transcript: str) -> str:
    """Generate a short summary of the IVR call transcript using Groq."""
    try:
        from groq import Groq
        import os
        client = Groq(api_key=os.getenv("IVR_GROQ_API_KEY"))
        prompt = f"Below is a transcript of an IVR call. Summarize what happened in the call in 1-2 simple sentences:\n\n{transcript}"
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ IVR summary generation failed: {e}")
        if "Meeting Booked" in transcript or "Scheduled" in transcript:
            return "Customer successfully scheduled a meeting."
        elif "Sales Team Requested" in transcript or "Sales" in transcript:
            return "Customer requested a call back from the Sales Team."
        return "IVR call completed."


async def get_request_data(request: Request) -> dict:
    """Helper to safely parse request body without causing Starlette hang."""
    if request.method == "GET":
        return dict(request.query_params)
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            return await request.json()
        except Exception:
            return {}
    else:
        try:
            return dict(await request.form())
        except Exception:
            return {}

def transcribe_audio_url(url: str) -> str:
    """Download audio from Vobiz and transcribe using Groq Whisper."""
    groq_client = Groq(api_key=os.getenv("IVR_GROQ_API_KEY"))
    try:
        print(f"⏳ Downloading audio for transcription: {url}")
        headers = {
            "X-Auth-ID": os.getenv("IVR_VOBIZ_AUTH_ID", ""),
            "X-Auth-Token": os.getenv("IVR_VOBIZ_AUTH_TOKEN", "")
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
                temp_audio.write(response.content)
                temp_audio_path = temp_audio.name
                
            with open(temp_audio_path, "rb") as file:
                transcription = groq_client.audio.transcriptions.create(
                    file=(os.path.basename(temp_audio_path), file.read()),
                    model="whisper-large-v3",
                    language="hi"
                )
            os.remove(temp_audio_path)
            print(f"✅ Transcription result: {transcription.text}")
            return transcription.text
        else:
            print(f"❌ Failed to download audio. Status: {response.status_code}, Msg: {response.text}")
    except Exception as e:
        print(f"❌ Transcription error: {e}")
    return ""

def parse_datetime_from_speech(speech: str) -> str:
    """Use Groq LLM to parse spoken date/time into YYYY-MM-DD HH:MM in Asia/Kolkata timezone."""
    kolkata_tz = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(kolkata_tz)
    
    groq_client = Groq(api_key=os.getenv("IVR_GROQ_API_KEY"))
    prompt = (
        f"Today is {now.strftime('%Y-%m-%d')} ({now.strftime('%A')}). "
        f"User said in Hindi/Hinglish: '{speech}'. "
        f"IMPORTANT Hindi time words:\n"
        f"- 'subah/savere' = morning = AM (e.g. subah 10 baje = 10:00)\n"
        f"- 'dopahar', 'do fair', 'do phair' = afternoon (e.g. do fair bara baje = 12:00 PM)\n"
        f"- 'sham/shaam' = evening = PM (e.g. sham 3 baje = 15:00)\n"
        f"- 'raat' = night = PM (e.g. raat 8 baje = 20:00)\n\n"
        f"IMPORTANT CONTEXT RULES:\n"
        f"1. In a meeting scheduling context, the Hindi word 'kal' (कल) ALWAYS means 'tomorrow' (future). It NEVER means 'yesterday'.\n"
        f"2. The scheduled meeting MUST ALWAYS be in the future (on or after today, {now.strftime('%Y-%m-%d')}). NEVER schedule a meeting in the past.\n\n"
        f"Extract the meeting date and time.\n"
        f"If the user DID NOT explicitly mention a specific day, date, or time (e.g., if they just said 'haan', 'theek hai', 'karte hain'), you MUST return exactly the word 'MISSING'.\n"
        f"If they did mention a time, return ONLY format 'YYYY-MM-DD HH:MM' (24-hour).\n"
        f"Return ONLY the datetime string or 'MISSING', nothing else."
    )
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20,
            temperature=0.1,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        next_day = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        return f"{next_day} 10:00"


# ─────────────────────────────────────────────
# DYNAMIC ROUTING ENDPOINTS
# ─────────────────────────────────────────────

@router.get("/dynamic_tts")
async def dynamic_tts(request: Request):
    """Streams TTS audio using ElevenLabs (primary) or Murf (fallback) for Indian languages."""
    text = request.query_params.get("text", "")
    lang = request.query_params.get("lang", "mr")

    if not text:
        return FastAPIResponse(status_code=400, content="Missing text parameter")

    elevenlabs_key = os.getenv("IVR_ELEVENLABS_API_KEY")
    tts_provider = os.getenv("TTS_PROVIDER", "elevenlabs").lower()

    # ── ElevenLabs (Primary — natural human voice, multilingual-v2) ──
    if elevenlabs_key and tts_provider == "elevenlabs":
        try:
            import httpx

            # Bella (EXAVITQu4vr4xnSDxMaL) — FREE default voice, works on free tier
            # eleven_multilingual_v2 model speaks Marathi, Gujarati, Punjabi naturally
            voice_id = "EXAVITQu4vr4xnSDxMaL"  # Bella — free default female voice

            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {
                "xi-api-key": elevenlabs_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            }
            payload = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.4,
                    "similarity_boost": 0.8,
                    "style": 0.3,
                    "use_speaker_boost": True
                }
            }

            # Fetch full audio first so we detect errors BEFORE returning response
            # This allows clean fallback to Murf if ElevenLabs fails
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, headers=headers, json=payload)

            if resp.status_code == 200:
                audio_bytes = resp.content
                print(f"[ElevenLabs TTS] OK — {len(audio_bytes)} bytes for lang={lang}")
                return FastAPIResponse(
                    content=audio_bytes,
                    media_type="audio/mpeg",
                    headers={"Content-Length": str(len(audio_bytes))}
                )
            else:
                print(f"[ElevenLabs TTS] Error {resp.status_code}: {resp.text} — falling back to Murf")

        except Exception as e:
            print(f"[ElevenLabs TTS] Exception: {e} — falling back to Murf")

    # ── Murf (Fallback) ──
    return StreamingResponse(generate_wav_stream(text, lang_code=lang, gender="female"), media_type="audio/wav")

@router.get("/start")
@router.post("/start")
async def start_flow(request: Request):
    """
    Entry point for the call.
    Vobiz/Twilio will hit this when the customer picks up.
    """
    data = await get_request_data(request)
    
    webhookId = request.query_params.get("webhookId", data.get("webhookId", ""))
    actionId = request.query_params.get("actionId", body.get("actionId", "") if "body" in locals() else data.get("actionId", "") if "data" in locals() else "")
    actionId = request.query_params.get("actionId", data.get("actionId", ""))
    name = request.query_params.get("name", data.get("name", "Customer"))
    call_uuid = data.get("CallUUID", data.get("call_uuid", ""))
    direction = data.get("Direction", data.get("direction", "")).lower()

    if direction == "outbound":
        phone_number = normalize_phone(data.get("To", data.get("to", "")))
        ivr_phone = normalize_phone(data.get("From", data.get("from", "")))
    else:
        phone_number = normalize_phone(data.get("From", data.get("from", "")))
        ivr_phone = normalize_phone(data.get("To", data.get("to", "")))

    if not ivr_phone:
        ivr_phone = normalize_phone(os.getenv("IVR_VOBIZ_PHONE_NUMBER", ""))

    if call_uuid:
        push_to_crm({
            "event_type": "call_picked_up",
            "call_uuid": call_uuid,
            "customer_phone": phone_number,
            "ivr_phone": ivr_phone,
            "customer_name": name,
            "actionId": actionId,
            "agent_type": "dynamic_node_ivr",
            "direction": direction if direction else "inbound"
        }, webhookId)

    lang = request.query_params.get("lang", data.get("lang", ""))
    flow = get_flow(webhookId, lang)
    start_node_id = flow.get("start_node", "node_greeting")
    
    print(f"📞 Dynamic Call started for webhookId: {webhookId}. Routing to {start_node_id} (Lang: {flow.get('language', 'hi')})")
    
    base_url = os.getenv("IVR_BASE_URL")
    encoded_name = urllib.parse.quote(name)
    
    lang_param = f"&amp;lang={lang}" if lang else ""
    
    xml = f"""
    <Response>
        <Redirect method="POST">{base_url}/ivr/node?node_id={start_node_id}&amp;webhookId={webhookId}&amp;name={encoded_name}&amp;actionId={actionId}{lang_param}</Redirect>
    </Response>
    """
    return xml_resp(xml)


@router.get("/node")
@router.post("/node")
async def play_node(request: Request):
    """
    Dynamically fetches and routes a node based on its type.
    """
    data = await get_request_data(request)
    query_params = dict(request.query_params)
    
    webhookId = query_params.get("webhookId", data.get("webhookId", ""))
    actionId = query_params.get("actionId", data.get("actionId", "") if "data" in locals() else "")
    node_id = query_params.get("node_id", "")
    name = urllib.parse.unquote(query_params.get("name", "Customer"))
    lang = query_params.get("lang", "")
    
    flow = get_flow(webhookId, lang)
    nodes = flow.get("nodes", {})
    flow_lang = flow.get("language", "hi")
    
    if node_id not in nodes:
        print(f"❌ Dynamic Node {node_id} not found in flow!")
        return xml_resp(f'<Response>{say("Error. Node not found.", flow_lang)}<Hangup/></Response>')

    current_node = nodes[node_id]
    node_type = current_node.get("type", "message")
    
    # Format text with dynamic variables
    text_to_speak = current_node.get("text", "")
    try:
        text_to_speak = text_to_speak.format(name=name)
    except Exception as e:
        print(f"⚠️ Text formatting error: {e}")
        
    base_url = os.getenv("IVR_BASE_URL")
    encoded_name = urllib.parse.quote(name)
    lang_param = f"&amp;lang={lang}" if lang else ""

    # Extract call tracking details for transcript logging
    call_uuid = data.get("CallUUID", data.get("call_uuid", ""))
    direction = data.get("Direction", data.get("direction", "")).lower()
    if direction == "outbound":
        phone_number = normalize_phone(data.get("To", data.get("to", "")))
    else:
        phone_number = normalize_phone(data.get("From", data.get("from", "")))

    # Log the played prompt step
    if text_to_speak:
        log_ivr_step(call_uuid, phone_number, "IVR", text_to_speak)

    # ────────────────────────────────────────────────────────
    # 1. MENU NODE (Interactive Multi-option digit input)
    # ────────────────────────────────────────────────────────
    if node_type == "menu":
        action_url = f"{base_url}/ivr/process_menu?node_id={node_id}&amp;webhookId={webhookId}&amp;actionId={actionId}&amp;name={encoded_name}{lang_param}"
        
        xml = f"""
        <Response>
            <GetDigits numDigits="1" timeout="10" finishOnKey="" retries="1" action="{action_url}" method="POST">
                {say(text_to_speak, flow_lang)}
            </GetDigits>
            {say(current_node.get("invalid_text", "कोई response नहीं मिली।"), flow_lang)}
            <Redirect method="POST">{base_url}/ivr/node?node_id={node_id}&amp;webhookId={webhookId}&amp;actionId={actionId}&amp;name={encoded_name}{lang_param}</Redirect>
        </Response>
        """
        # Send prompt information to CRM with unified naming
        push_to_crm({
            "actionId": actionId,
            "event_type": "ivr_prompt",
            "node_id": node_id,
            # "prompt_text": text_to_speak,
            # "prompt": text_to_speak,
            "transcript": text_to_speak,
            "customer_name": name,
            "agent_type": "dynamic_node_ivr"
        }, webhookId)
        return xml_resp(xml)

    # ────────────────────────────────────────────────────────
    # 2. RECORD NODE (Asks for meeting details & records speech)
    # ────────────────────────────────────────────────────────
    elif node_type == "action_record":
        action_url = f"{base_url}/ivr/confirm?node_id={node_id}&amp;webhookId={webhookId}&amp;actionId={actionId}&amp;name={encoded_name}{lang_param}"
        fallback_url = f"{base_url}/ivr/fallback_time?node_id={node_id}&amp;webhookId={webhookId}&amp;actionId={actionId}&amp;name={encoded_name}{lang_param}"
        
        # Send prompt information to CRM with unified naming
        push_to_crm({
            "actionId": actionId,
            "event_type": "ivr_prompt",
            "node_id": node_id,
            "transcript": text_to_speak,
            "customer_name": name,
            "agent_type": "dynamic_node_ivr"
        }, webhookId)

        xml = f"""
        <Response>
            {say(text_to_speak, flow_lang)}
            <Record action="{action_url}" method="POST" maxLength="15" timeout="4" playBeep="true" />
            <Redirect method="POST">{fallback_url}</Redirect>
        </Response>
        """
        return xml_resp(xml)

    # ────────────────────────────────────────────────────────
    # 3. ACTION BOOK MEETING (End state plays confirmation message)
    # ────────────────────────────────────────────────────────
    elif node_type == "action_book_meeting":
        xml = f"""
        <Response>
            {say(text_to_speak, flow_lang)}
        </Response>
        """
        next_node_id = current_node.get("next_node", current_node.get("next", ""))
        if next_node_id:
            xml = xml.replace("</Response>", f'<Redirect method="POST">{base_url}/ivr/node?node_id={next_node_id}&amp;webhookId={webhookId}&amp;actionId={actionId}&amp;name={encoded_name}{lang_param}</Redirect></Response>')
        else:
            xml = xml.replace("</Response>", "<Hangup/></Response>")
            
        return xml_resp(xml)

    # ────────────────────────────────────────────────────────
    # 4. ACTION FORWARD NODE (Tags Lead & routes to Sales)
    # ────────────────────────────────────────────────────────
    elif node_type == "action_forward":
        call_uuid = data.get("CallUUID", data.get("call_uuid", ""))
        direction = data.get("Direction", data.get("direction", "")).lower()
        if direction == "outbound":
            phone_number = normalize_phone(data.get("To", data.get("to", "")))
            ivr_phone = normalize_phone(data.get("From", data.get("from", "")))
        else:
            phone_number = normalize_phone(data.get("From", data.get("from", "")))
            ivr_phone = normalize_phone(data.get("To", data.get("to", "")))

        if not ivr_phone:
            ivr_phone = normalize_phone(os.getenv("IVR_VOBIZ_PHONE_NUMBER", ""))

        # Check if the node specifies a forwarding number, else fallback
        forward_number = current_node.get("forward_number", "")

        # Log system message
        log_ivr_step(call_uuid, phone_number, "System", f"Action Forward executed. Forwarding to {forward_number if forward_number else 'No number, Hanging up'}.")

        # Get full transcript
        full_transcript = get_ivr_transcript(call_uuid, phone_number)
        summary = summarize_ivr_call(full_transcript)

        push_to_crm({
            "actionId": actionId,
            "event_type": "call_summary",
            "call_uuid": call_uuid,
            "customer_phone": phone_number,
            "ivr_phone": ivr_phone,
            "customer_name": name,
            "final_status": "Call Forwarded / Action Complete",
            "transcript": full_transcript,
            "summary": summary
        }, webhookId)

        if forward_number:
            # Ensure forward_number has + sign (E.164 format) as requested by Vobiz Support
            if not forward_number.startswith("+"):
                forward_number = f"+{forward_number}"
                
            auth_id = os.getenv("IVR_VOBIZ_AUTH_ID")
            auth_token = os.getenv("IVR_VOBIZ_AUTH_TOKEN")
            
            # Fire API call asynchronously to transfer
            def trigger_transfer():
                transfer_url = f"{base_url}/ivr/transfer_xml?number={forward_number}&callerId={ivr_phone}"
                api_url = f"https://api.vobiz.ai/api/v1/Account/{auth_id}/Call/{call_uuid}/"
                print(f"🔄 Triggering Vobiz Transfer API: {api_url} to {forward_number} with callerId {ivr_phone}")
                try:
                    res = requests.post(
                        api_url,
                        json={"url": transfer_url},
                        headers={"X-Auth-ID": auth_id, "X-Auth-Token": auth_token, "Content-Type": "application/json"},
                        timeout=5
                    )
                    print(f"🔄 Transfer API Response: {res.status_code} - {res.text}")
                except Exception as e:
                    print(f"❌ Transfer API Error: {e}")
                    
            if call_uuid and call_uuid != "unknown":
                asyncio.create_task(asyncio.to_thread(trigger_transfer))
                
            xml = f"""
            <Response>
                {say(text_to_speak, flow_lang)}
                <Pause length="10"/>
            </Response>
            """
        else:
            xml = f"""
            <Response>
                {say(text_to_speak, flow_lang)}
                <Hangup/>
            </Response>
            """
        return xml_resp(xml)
        
    else:
        xml = f"""
        <Response>
            {say(text_to_speak, flow_lang)}
        </Response>
        """
        next_node_id = current_node.get("next_node", current_node.get("next", ""))
        if next_node_id:
            xml = xml.replace("</Response>", f'<Redirect method="POST">{base_url}/ivr/node?node_id={next_node_id}&amp;webhookId={webhookId}&amp;actionId={actionId}&amp;name={encoded_name}{lang_param}</Redirect></Response>')
        else:
            xml = xml.replace("</Response>", "<Hangup/></Response>")
        return xml_resp(xml)


@router.get("/process_menu")
@router.post("/process_menu")
async def process_menu(request: Request):
    """
    Receives the Gather input digit, checks branches, and advances node.
    """
    data = await get_request_data(request)
    query_params = dict(request.query_params)
    print(f"🔍 [DEBUG process_menu] data={data}")
    print(f"🔍 [DEBUG process_menu] query_params={query_params}")
    
    webhookId = query_params.get("webhookId", "")
    actionId = query_params.get("actionId", data.get("actionId", "") if "data" in locals() else "")
    node_id = query_params.get("node_id", "")
    name = urllib.parse.unquote(query_params.get("name", "Customer"))
    lang = query_params.get("lang", "")
    digit_pressed = str(data.get("Digits", data.get("digits", ""))).strip()
    if digit_pressed:
        digit_pressed = digit_pressed[0] # Handle DTMF bounce (e.g. '11' -> '1')
    
    flow = get_flow(webhookId, lang)
    nodes = flow.get("nodes", {})
    current_node = nodes.get(node_id, {})
    flow_lang = flow.get("language", "hi")
    
    raw_branches = current_node.get("branches", {})
    # MongoDB may store branch keys as integers (e.g. {1: "node_xyz"}) instead of strings.
    # Normalize all keys to strings so the lookup "1" in {"1": ...} always works.
    branches = {str(k): v for k, v in raw_branches.items()}
    base_url = os.getenv("IVR_BASE_URL")
    encoded_name = urllib.parse.quote(name)
    lang_param = f"&amp;lang={lang}" if lang else ""

    print(f"🔍 [DEBUG] digit_pressed='{digit_pressed}' (type={type(digit_pressed).__name__}), branches keys={list(branches.keys())}, raw keys={list(raw_branches.keys())}")

    if digit_pressed in branches:
        next_node_id = branches[digit_pressed]
        print(f"👉 User pressed digit {digit_pressed}. Jumping to node: {next_node_id}")
        
        call_uuid = data.get("CallUUID", data.get("call_uuid", ""))
        direction = data.get("Direction", data.get("direction", "")).lower()
        if direction == "outbound":
            phone_number = normalize_phone(data.get("To", data.get("to", "")))
            ivr_phone = normalize_phone(data.get("From", data.get("from", "")))
        else:
            phone_number = normalize_phone(data.get("From", data.get("from", "")))
            ivr_phone = normalize_phone(data.get("To", data.get("to", "")))

        if not ivr_phone:
            ivr_phone = normalize_phone(os.getenv("IVR_VOBIZ_PHONE_NUMBER", ""))

        raw_tags = current_node.get("tags", {})
        tags = {str(k): v for k, v in raw_tags.items()}
        tag_name = tags.get(digit_pressed, f"Selected Option {digit_pressed}")
        
        # Log customer press
        log_ivr_step(call_uuid, phone_number, "Customer", f"Pressed {digit_pressed} ({tag_name})")

        push_to_crm({
            "actionId": actionId,
            "event_type": "lead_tag",
            "call_uuid": call_uuid,
            "customer_phone": phone_number,
            "ivr_phone": ivr_phone,
            "customer_name": name,
            "tag": tag_name,
            "key_pressed": digit_pressed
        }, webhookId)

        prompt_text = current_node.get("text", "")
        push_to_crm({
            "actionId": actionId,
            "event_type": "ivr_response",
            "node_id": node_id,
            # "prompt_text": prompt_text,
            # "prompt": prompt_text,
            "transcript": prompt_text,
            "digit_pressed": digit_pressed,
            "customer_name": name,
            "agent_type": "dynamic_node_ivr"
        }, webhookId)

        # Push IVR response to Viasocket for Google Sheets automation
        push_to_viasocket({
            "customer_name": name,
            "customer_phone": phone_number,
            "digit_pressed": digit_pressed
        })

        xml = f"""
        <Response>
            <Redirect method="POST">{base_url}/ivr/node?node_id={next_node_id}&amp;webhookId={webhookId}&amp;actionId={actionId}&amp;name={encoded_name}{lang_param}</Redirect>
        </Response>
        """
        return xml_resp(xml)
    else:
        print(f"⚠️ User pressed invalid button: {digit_pressed}")
        invalid_text = current_node.get("invalid_text", "Invalid option. कृपया 1 या 2 दबाएँ।")
        
        # We need call_uuid and phone to log invalid presses too
        call_uuid = data.get("CallUUID", data.get("call_uuid", ""))
        direction = data.get("Direction", data.get("direction", "")).lower()
        if direction == "outbound":
            phone_number = normalize_phone(data.get("To", data.get("to", "")))
        else:
            phone_number = normalize_phone(data.get("From", data.get("from", "")))
            
        log_ivr_step(call_uuid, phone_number, "Customer", f"Pressed invalid key: {digit_pressed}")
        log_ivr_step(call_uuid, phone_number, "IVR", invalid_text)
        
        action_url = f"{base_url}/ivr/process_menu?node_id={node_id}&amp;webhookId={webhookId}&amp;actionId={actionId}&amp;name={encoded_name}{lang_param}"
        xml = f"""
        <Response>
            <GetDigits numDigits="1" timeout="10" action="{action_url}" method="POST">
                {say(invalid_text, flow_lang)}
            </GetDigits>
            {say(invalid_text, flow_lang)}
            <Redirect method="POST">{base_url}/ivr/node?node_id={node_id}&amp;webhookId={webhookId}&amp;actionId={actionId}&amp;name={encoded_name}{lang_param}</Redirect>
        </Response>
        """
        return xml_resp(xml)


background_booking_tasks = {}

async def process_booking_background(data, query_params, call_uuid, phone_number, ivr_phone, base_url, node_id, webhookId, encoded_name, name, flow_lang, flow):
    actionId = query_params.get("actionId", data.get("actionId", ""))
    record_url = data.get("RecordFile", data.get("RecordUrl", data.get("RecordingUrl", "")))
    if record_url:
        time_speech = await asyncio.to_thread(transcribe_audio_url, record_url)
    else:
        time_speech = data.get("SpeechResult", data.get("speech_result", "")).strip()

    if not time_speech:
        log_ivr_step(call_uuid, phone_number, "Customer (Voice)", "[No speech detected]")
        return f"""<Response><Redirect method="POST">{base_url}/ivr/fallback_time?node_id={node_id}&amp;name={encoded_name}&amp;webhookId={webhookId}&amp;actionId={actionId}</Redirect></Response>"""

    log_ivr_step(call_uuid, phone_number, "Customer (Voice)", time_speech)
    push_to_crm({
        "actionId": actionId,
            "event_type": "ivr_response",
        "node_id": node_id,
        "transcript": time_speech,
        "customer_name": name,
        "agent_type": "dynamic_node_ivr"
    }, webhookId)

    dt_str = await asyncio.to_thread(parse_datetime_from_speech, time_speech)
    if dt_str == "MISSING" or not dt_str:
        log_ivr_step(call_uuid, phone_number, "System Parsed", f"Failed to parse time from speech: '{time_speech}'")
        return f"""<Response><Redirect method="POST">{base_url}/ivr/fallback_time?node_id={node_id}&amp;name={encoded_name}&amp;webhookId={webhookId}&amp;actionId={actionId}</Redirect></Response>"""

    # Check calendar availability
    from calendar_api import get_calendar_service
    try:
        service = get_calendar_service()
        kolkata_tz = timezone(timedelta(hours=5, minutes=30))
        start_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=kolkata_tz)
        end_dt = start_dt + timedelta(minutes=30)
        
        events_result = await asyncio.to_thread(
            lambda: service.events().list(
                calendarId="primary",
                timeMin=start_dt.isoformat(),
                timeMax=end_dt.isoformat(),
                singleEvents=True
            ).execute()
        )
        existing_events = events_result.get("items", [])
        if existing_events:
            print(f"⚠️ Conflict found during call: {len(existing_events)} overlapping events at {dt_str}")
            log_ivr_step(call_uuid, phone_number, "System Parsed", f"Time conflict at {dt_str}. Overlapping event count: {len(existing_events)}")
            if flow_lang == "en":
                conflict_msg = "Sorry, we have another meeting scheduled at that time."
            elif flow_lang == "mr":
                conflict_msg = "क्षमस्व, त्या वेळी आमची दुसरी मीटिंग शेड्यूल केलेली आहे."
            else:
                conflict_msg = "माफ़ कीजिए, उस समय पर हमारी एक और मीटिंग शेड्यूल है।"
            log_ivr_step(call_uuid, phone_number, "IVR", conflict_msg)
            return f"""<Response>
    {say(conflict_msg, flow_lang)}
    <Redirect method="POST">{base_url}/ivr/fallback_time?node_id={node_id}&amp;name={encoded_name}&amp;webhookId={webhookId}&amp;actionId={actionId}&amp;conflict=1</Redirect>
</Response>"""
    except Exception as e:
        print(f"⚠️ Calendar verification failed: {e}")

    try:
        friendly_time = datetime.strptime(dt_str, "%Y-%m-%d %H:%M").strftime("%d %B %Y at %I:%M %p")
    except Exception:
        friendly_time = dt_str

    async def finalize_booking():
        try:
            result = await asyncio.to_thread(book_meeting, name, dt_str)
            print(f"📅 Background Booking: {name} | {dt_str} | {result}")
            
            if result != "ERROR_ALREADY_BOOKED":
                log_ivr_step(call_uuid, phone_number, "System Parsed", f"Scheduled on {friendly_time}")
                
                full_transcript = get_ivr_transcript(call_uuid, phone_number)
                summary = summarize_ivr_call(full_transcript)
                
                push_to_crm({
                    "actionId": actionId,
            "event_type": "call_summary",
                    "call_uuid": call_uuid,
                    "customer_phone": phone_number,
                    "ivr_phone": ivr_phone,
                    "customer_name": name,
                    "final_status": "Meeting Booked",
                    "meeting_time": friendly_time,
                    "transcript": full_transcript,
                    "summary": summary
                }, webhookId)
        except Exception as e:
            print(f"❌ Background booking error: {e}")

    asyncio.create_task(finalize_booking())

    nodes = flow.get("nodes", {})
    current_node = nodes.get(node_id, {})
    next_node_id = current_node.get("next_node", current_node.get("next", ""))

    if next_node_id:
        xml = f"""
        <Response>
            <Redirect method="POST">{base_url}/ivr/node?node_id={next_node_id}&amp;webhookId={webhookId}&amp;actionId={actionId}&amp;name={encoded_name}</Redirect>
        </Response>
        """
    else:
        if flow_lang == "en":
            goodbye_1 = f"Excellent {name}, we have received your request for {friendly_time}."
            goodbye_2 = "Our team will check the calendar and send you an SMS shortly. Thank you!"
        elif flow_lang == "mr":
            goodbye_1 = f"उत्तम {name}, आम्हाला तुमची {friendly_time} ची विनंती मिळाली आहे."
            goodbye_2 = "आमची टीम लवकरच कॅलेंडर तपासेल आणि तुम्हाला SMS पाठवेल. धन्यवाद!"
        else:
            goodbye_1 = f"बहुत अच्छा! {name} जी, हमने आपकी {friendly_time} की request ले ली है।"
            goodbye_2 = "हमारी team जल्द ही calendar check करके आपको SMS भेज देगी। बिंजवा IT Solutions को समय देने के लिए धन्यवाद!"
        
        log_ivr_step(call_uuid, phone_number, "IVR", f"{goodbye_1} {goodbye_2}")

        xml = f"""
        <Response>
            {say(goodbye_1, flow_lang)}
            {say(goodbye_2, flow_lang)}
            <Hangup/>
        </Response>
        """
    return xml


@router.post("/confirm")
async def confirm_recording(request: Request):
    """
    Spawns background task for heavy processing and instantly plays waiting message.
    """
    base_url = os.getenv("IVR_BASE_URL", "")
    data = await get_request_data(request)
    query_params = dict(request.query_params)
    
    node_id = query_params.get("node_id", "")
    webhookId = query_params.get("webhookId", "")
    actionId = query_params.get("actionId", data.get("actionId", "") if "data" in locals() else "")
    name = urllib.parse.unquote(query_params.get("name", "Customer"))
    encoded_name = urllib.parse.quote(name)
    
    flow = get_flow(webhookId)
    flow_lang = flow.get("language", "hi")

    print(f"🎙️ [DYNAMIC RECORD CONFIRM]: {data}")

    call_uuid = data.get("CallUUID", data.get("call_uuid", ""))
    direction = data.get("Direction", data.get("direction", "")).lower()
    if direction == "outbound":
        phone_number = normalize_phone(data.get("To", data.get("to", "")))
        ivr_phone = normalize_phone(data.get("From", data.get("from", "")))
    else:
        phone_number = normalize_phone(data.get("From", data.get("from", "")))
        ivr_phone = normalize_phone(data.get("To", data.get("to", "")))

    if not ivr_phone:
        ivr_phone = normalize_phone(os.getenv("IVR_VOBIZ_PHONE_NUMBER", ""))

    # Start the heavy processing in the background
    background_booking_tasks[call_uuid] = asyncio.create_task(
        process_booking_background(
            data, query_params, call_uuid, phone_number, ivr_phone, base_url, node_id, webhookId, encoded_name, name, flow_lang, flow
        )
    )

    # Play a short waiting message immediately
    if flow_lang == "en":
        wait_msg = "Please wait, we are checking your calendar."
    elif flow_lang == "mr":
        wait_msg = "कृपया प्रतीक्षा करा, आम्ही तुमचे कॅलेंडर तपासत आहोत."
    else:
        wait_msg = "कृपया, हम आपके कैलेंडर की जाँच कर रहे हैं, थोड़ा इंतजार करें।"
    
    log_ivr_step(call_uuid, phone_number, "IVR", wait_msg)
    checking_voice = say(wait_msg, flow_lang)
    
    return xml_resp(f"""<Response>
    {checking_voice}
    <Redirect method="POST">{base_url}/ivr/process_booking_result?call_uuid={call_uuid}</Redirect>
</Response>""")


@router.post("/process_booking_result")
async def process_booking_result(request: Request):
    """
    Awaits the background task and returns the actual booking result XML.
    """
    query_params = dict(request.query_params)
    call_uuid = query_params.get("call_uuid", "")
    
    task = background_booking_tasks.get(call_uuid)
    if not task:
        # Fallback if task somehow doesn't exist
        print(f"⚠️ No background task found for call {call_uuid}")
        return xml_resp("<Response><Hangup/></Response>")
        
    try:
        xml_content = await task
    except Exception as e:
        print(f"❌ Background process failed: {e}")
        xml_content = "<Response><Hangup/></Response>"
        
    # Clean up dictionary
    if call_uuid in background_booking_tasks:
        del background_booking_tasks[call_uuid]
        
    return xml_resp(xml_content)


@router.post("/fallback_time")
async def fallback_recording(request: Request):
    """
    Handles speech parsing fallback/retries and calendar conflicts.
    """
    base_url = os.getenv("IVR_BASE_URL", "")
    data = await get_request_data(request)
    query_params = dict(request.query_params)
    
    node_id = query_params.get("node_id", "")
    name = urllib.parse.unquote(query_params.get("name", "Customer"))
    encoded_name = urllib.parse.quote(name)
    retry = int(query_params.get("retry", "0"))
    webhookId = query_params.get("webhookId", "")
    actionId = query_params.get("actionId", data.get("actionId", "") if "data" in locals() else "")
    conflict = query_params.get("conflict", "")

    # Retrieve call tracking info
    call_uuid = data.get("CallUUID", data.get("call_uuid", ""))
    direction = data.get("Direction", data.get("direction", "")).lower()
    if direction == "outbound":
        phone_number = normalize_phone(data.get("To", data.get("to", "")))
    else:
        phone_number = normalize_phone(data.get("From", data.get("from", "")))

    flow = get_flow(webhookId)
    flow_lang = flow.get("language", "hi")

    if retry >= 2:
        if flow_lang == "en":
            goodbye_prompt = f"No problem {name}. You can call us back later. Thank you for giving your time to Binjwa IT Solutions. Have a great day."
        elif flow_lang == "mr":
            goodbye_prompt = f"काही हरकत नाही {name}. तुम्ही आम्हाला नंतर कॉल करू शकता. बिंजवा IT Solutions ला तुमचा वेळ दिल्याबद्दल धन्यवाद. तुमचा दिवस शुभ असो."
        else:
            goodbye_prompt = f"कोई बात नहीं {name} जी। आप बाद में हमें call कर सकते हैं। बिंजवा IT Solutions को समय देने के लिए बहुत धन्यवाद। आपका दिन शुभ हो।"
        log_ivr_step(call_uuid, phone_number, "IVR", goodbye_prompt)
        return xml_resp(f"""<Response>
    {say(goodbye_prompt, flow_lang)}
    <Hangup/>
</Response>""")

    if conflict:
        if flow_lang == "en":
            prompt = "Please suggest another day or time between Monday and Friday when you would like to meet."
        elif flow_lang == "mr":
            prompt = "कृपया सोमवार ते शुक्रवार दरम्यान दुसरा एखादा दिवस किंवा वेळ सांगा जेव्हा तुम्हाला मीटिंग करायला आवडेल."
        else:
            prompt = "कृपया सोमवार से शुक्रवार के बीच कोई दूसरा दिन या समय बताएँ जब आप मीटिंग करना चाहते हैं।"
    else:
        if flow_lang == "en":
            prompt = "Sorry, I didn't catch that. Could you please repeat what day and time between Monday and Friday you would like to schedule the meeting?"
        elif flow_lang == "mr":
            prompt = "क्षमस्व, मला ऐकू आले नाही, तुम्ही सोमवार ते शुक्रवार दरम्यान कोणत्या दिवशी आणि किती वाजता मीटिंग शेड्यूल करू इच्छिता ते पुन्हा सांगू शकाल का?"
        else:
            prompt = "माफ़ कीजिए, मुझे सुनाई नहीं दिया, क्या आप रिपीट कर सकते हैं कि आप सोमवार से शुक्रवार के बीच किस दिन और कितने बजे मीटिंग करना चाहते हैं?"

    # Log fallback prompt played
    log_ivr_step(call_uuid, phone_number, "IVR", prompt)

    action_url = f"{base_url}/ivr/confirm?node_id={node_id}&amp;webhookId={webhookId}&amp;actionId={actionId}&amp;name={encoded_name}"
    fallback_url = f"{base_url}/ivr/fallback_time?node_id={node_id}&amp;retry={retry + 1}&amp;webhookId={webhookId}&amp;actionId={actionId}&amp;name={encoded_name}"

    return xml_resp(f"""<Response>
    {say(prompt, flow_lang)}
    <Record action="{action_url}" method="POST" maxLength="15" timeout="4" playBeep="true" />
    <Redirect method="POST">{fallback_url}</Redirect>
</Response>""")


@router.post("/trigger_single_call")
async def trigger_single_call(request: Request):
    """
    Allows the CRM developer to trigger an outbound test call
    that connects directly to the new dynamic Node Engine!
    """
    data = await get_request_data(request)
    
    phone = data.get("phone", data.get("phone_number", "")).strip()
    name = data.get("name", data.get("customer_name", "Customer"))
    webhookId = data.get("webhookId", "")
    actionId = data.get("actionId", "")
    
    if not phone:
        return {"status": "error", "detail": "Phone number is required."}
        
    if len(phone) == 10 and phone.isdigit():
        phone = f"+91{phone}"
    elif len(phone) == 12 and phone.startswith("91"):
        phone = f"+{phone}"
        
    base_url = os.getenv("IVR_BASE_URL")
    auth_id = os.getenv("IVR_VOBIZ_AUTH_ID")
    auth_token = os.getenv("IVR_VOBIZ_AUTH_TOKEN")
    vobiz_phone = os.getenv("IVR_VOBIZ_PHONE_NUMBER", "+911171366938")
    
    lang = data.get("lang", "")
    
    url = f"https://api.vobiz.ai/api/v1/Account/{auth_id}/Call/"
    encoded_name = urllib.parse.quote(name)
    lang_param = f"&lang={lang}" if lang else ""
    
    payload = {
        "from": vobiz_phone,
        "to": phone,
        "answer_url": f"{base_url}/ivr/start?webhookId={webhookId}&name={encoded_name}&actionId={actionId}{lang_param}",
        "answer_method": "GET",
        "hangup_url": f"{base_url}/ivr/hangup?webhookId={webhookId}&actionId={actionId}",
        "hangup_method": "POST"
    }
    
    def make_call():
        return requests.post(url, json=payload, headers={"X-Auth-ID": auth_id, "X-Auth-Token": auth_token, "Content-Type": "application/json"})
        
    res = await asyncio.to_thread(make_call)
    
    if res.status_code in [200, 201]:
        print(f"📞 Dynamic Outbound Call triggered to {name} ({phone}) for webhookId {webhookId}")
        
        call_uuid = "unknown"
        try:
            call_uuid = res.json().get("call_uuid", "unknown")
        except:
            pass
            
        push_to_crm({
            "actionId": actionId,
            "event_type": "call_initiated",
            "call_uuid": call_uuid,
            "customer_phone": phone,
            "ivr_phone": vobiz_phone,
            "customer_name": name,
            "agent_type": "dynamic_node_ivr"
        }, webhookId)

        return {"status": "success", "message": f"Single call triggered successfully to {name}"}
    else:
        print(f"❌ Failed to trigger dynamic call: {res.status_code} - {res.text}")
        return {"status": "error", "detail": "Failed to trigger call with Vobiz"}


@router.post("/trigger_campaign")
async def trigger_campaign(request: Request):
    """
    Triggers a mass sequential campaign using the dynamic Node tree for the given webhookId.
    """
    global CAMPAIGN_VOICE
    data = await request.json()
    
    # Update voice if provided by dashboard
    voice = data.get("voice")
    if voice:
        CAMPAIGN_VOICE = voice
        print(f"🎙️ Voice switched to: {CAMPAIGN_VOICE}")
        
    webhookId = data.get("webhookId", "")
    actionId = data.get("actionId", "")
    leads = data.get("leads", [])
    
    # Attach root webhookId and actionId to each lead if not present
    for lead in leads:
        if not lead.get("webhookId"):
            lead["webhookId"] = webhookId
        if not lead.get("actionId"):
            lead["actionId"] = actionId
            
    print(f"📥 Received {len(leads)} leads for campaign (webhookId: {webhookId}). Adding to queue...")
    campaign_queue.add_leads(leads)
    return {"status": "started", "queued": len(leads), "voice": CAMPAIGN_VOICE}

@router.api_route("/transfer_xml", methods=["GET", "POST"])
async def transfer_xml(request: Request):
    query_params = request.query_params
    number = query_params.get("number", "")
    caller_id = query_params.get("callerId", "")
    if not number.startswith("+") and number:
        number = f"+{number}"
        
    dial_attr = f' callerId="{caller_id}"' if caller_id else ""
    
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial{dial_attr}>
        <Number>{number}</Number>
    </Dial>
</Response>"""
    return FastAPIResponse(content=xml, media_type="text/xml")

@router.post("/hangup")
async def ivr_hangup(request: Request):
    """Triggered by Vobiz when the IVR call ends. Triggers the next queued call."""
    try:
        body = await request.json()
    except Exception:
        try:
            body = dict(await request.form())
        except Exception:
            body = dict(request.query_params)
    
    call_uuid = body.get("CallUUID", body.get("call_uuid", "unknown"))
    
    # Correctly identify IVR phone and Customer phone based on direction
    direction = body.get("Direction", body.get("direction", "")).lower()
    if direction == "outbound":
        ivr_phone = body.get("From", body.get("from", ""))
        customer_phone = body.get("To", body.get("to", ""))
    else:
        ivr_phone = body.get("To", body.get("to", ""))
        customer_phone = body.get("From", body.get("from", ""))
        
    if not ivr_phone:
        ivr_phone = os.getenv("IVR_VOBIZ_PHONE_NUMBER")
        
    webhookId = request.query_params.get("webhookId", body.get("webhookId", ""))
    actionId = request.query_params.get("actionId", body.get("actionId", "") if "body" in locals() else data.get("actionId", "") if "data" in locals() else "")
    print(f"📴 [IVR HANGUP] Call ended ({call_uuid}). Checking queue...")
    
    push_to_crm({
        "actionId": actionId,
            "event_type": "call_disconnected",
        "call_uuid": call_uuid,
        "ivr_phone": ivr_phone,
        "customer_phone": customer_phone,
        "agent_type": "dynamic_node_ivr"
    }, webhookId)
    
    # Signal the campaign queue that this call fully ended
    campaign_queue.on_call_ended()
    
    # Clean up log memory to prevent memory leaks
    if call_uuid and call_uuid in ivr_call_logs:
        try:
            del ivr_call_logs[call_uuid]
        except Exception:
            pass
            
    return {"status": "ok"}
