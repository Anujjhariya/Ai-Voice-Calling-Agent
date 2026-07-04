"""
ivr.py
------
IVR (Interactive Voice Response) system for Binjwa IT Solutions.
Uses Twilio TwiML <Gather> for key-press navigation. Completely
separate from the AI WebSocket agent in main.py.

Flow:
  /ivr/welcome       → Greeting + Main Menu
  /ivr/menu          → Main Menu (Press 1-4)
  /ivr/handle_menu   → Routes to service page
  /ivr/service/{key} → Short service info + Sub-menu
  /ivr/handle_service/{key} → Sub-menu (1=book, 2=more, 3=exit, 0=back)
  /ivr/more/{key}    → Detailed info + Sub-menu
  /ivr/book/{key}    → Ask name (speech)
  /ivr/book_time/{key} → Ask preferred time (speech)
  /ivr/confirm/{key} → Parse time, book meeting, confirm
  /ivr/goodbye       → Thank you + hangup

Included in main.py via:
  from ivr import router as ivr_router
  app.include_router(ivr_router)
"""

import os
import urllib.parse
import requests
import tempfile
import asyncio
from datetime import datetime, timedelta
import asyncio
from groq import Groq
from fastapi import APIRouter, Request
from fastapi.responses import Response as FastAPIResponse
from fastapi.responses import StreamingResponse
from tts import generate_wav_stream
import io
from twilio.rest import Client
from groq import Groq
from dotenv import load_dotenv
from calendar_api import book_meeting
from outbound_vobiz_ivr import make_vobiz_ivr_call

load_dotenv(override=True)

def push_to_crm(payload: dict, webhookId: str = ""):
    """Push event data to the CRM Webhook dynamically based on webhookId."""
    crm_base_url = os.getenv("IVR_CRM_BASE_URL", "").strip()
    
    # Fallback to old behavior if no webhookId is provided, for backwards compatibility
    if not webhookId:
        webhook_url = os.getenv("IVR_CRM_WEBHOOK_URL", "").strip()
    else:
        # Strip trailing slash if present, then append the dynamic path
        if crm_base_url.endswith('/'):
            crm_base_url = crm_base_url[:-1]
        webhook_url = f"{crm_base_url}/api/ivr-agent/voice/{webhookId}"

    if not webhook_url:
        return
        
    def do_push():
        try:
            import requests
            res = requests.post(webhook_url, json=payload, 
                                headers={"Content-Type": "application/json"},
                                timeout=3)  # 3 second max - never block the IVR
            print(f"🌐 [CRM Webhook] {payload.get('event_type')}: HTTP {res.status_code} ({webhook_url})")
        except Exception as e:
            print(f"⚠️ [CRM Webhook] Skipped ({e.__class__.__name__})")
            
    asyncio.create_task(asyncio.to_thread(do_push))

def normalize_phone(phone: str) -> str:
    """Ensure phone number always starts with '+'. Vobiz omits it in some webhooks."""
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

router = APIRouter(prefix="/ivr", tags=["IVR"])

# ─────────────────────────────────────────────
# SERVICE CONTENT  (Hinglish)
# ─────────────────────────────────────────────
IVR_SERVICES = {
    "1": {
        "name": "Software Services",
        "short": (
            "हम आपके business के लिए custom software solutions बनाते हैं — "
            # "जैसे billing system, ERP, inventory management और HR software। "
            # "Pricing start होती है Rs 15,000 से, और delivery time है 4 से 8 हफ्ते।"
        ),
        "detail": (
            "हमारी experienced team ने 50 से ज़्यादा businesses के लिए software बनाए हैं। "
            "हम Python, Java, और modern web technologies use करते हैं। "
            "हर project के साथ free training, documentation, और lifetime support भी मिलती है।"
        ),
    },
    "2": {
        "name": "Digital Marketing",
        "short": (
            "हम SEO, Google Ads, social media management और content marketing करते हैं। "
            "Monthly plans Rs 5,000 से शुरू होते हैं। "
            "हम आपकी online presence बढ़ाकर genuine customers तक पहुँचाते हैं।"
        ),
        "detail": (
            "हमारे clients को average 3 गुना ज़्यादा traffic मिला है पहले 3 महीनों में। "
            "हम Facebook, Instagram, LinkedIn और Google Ads पर targeted campaigns run करते हैं। "
            "हर महीने detailed performance report दी जाती है।"
        ),
    },
    "3": {
        "name": "Logo Designing",
        "short": (
            "Professional logo design starting from Rs 1,500। "
            "हम 3 unique concepts देते हैं, unlimited revisions के साथ। "
            "Delivery होती है 3 से 5 business days में।"
        ),
        "detail": (
            "आपको सभी formats मिलते हैं — PNG, JPG, SVG और print-ready PDF। "
            "साथ में brand color palette और typography guide भी include है। "
            "हमारे designers ने 200 से ज़्यादा brands के logos बनाए हैं।"
        ),
    },
    "4": {
        "name": "Website Design",
        "short": (
            "Professional websites starting from Rs 8,000। "
            "E-commerce store, business portfolio, या landing page — सब बनाते हैं। "
            "Mobile-friendly, fast और SEO-optimized websites हमारी specialty है।"
        ),
        "detail": (
            "हम WordPress, custom HTML CSS और React-based websites बनाते हैं। "
            "SSL certificate, 1 साल free hosting और Google Analytics setup भी मिलता है। "
            "Delivery होती है 1 से 2 हफ्ते में। हमने 100 से ज़्यादा businesses की websites बनाई हैं।"
        ),
    },
}

# Global setting for the currently selected voice
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
        print(f"\n[CAMPAIGN QUEUE] Dialing {name} at {phone}... ({len(self.leads)} remaining)\n")

        try:
            await asyncio.to_thread(make_vobiz_ivr_call, phone, name, CAMPAIGN_VOICE, webhookId)
            self.is_dialing = False
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


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def xml_resp(content: str) -> FastAPIResponse:
    # Remove all newlines and join
    xml_body = "".join(content.splitlines()).strip()
    # Remove extra spaces and spaces between tags
    import re
    xml_body = re.sub(r'>\s+<', '><', xml_body)
    xml_body = xml_body.strip()
    
    # Prepend XML declaration for Vobiz
    if not xml_body.startswith("<?xml"):
        xml_body = f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_body}'
        
    print(f"\n📡 [IVR XML RESPONSE]:\n{xml_body}\n")
    return FastAPIResponse(content=xml_body, media_type="text/xml")

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

def say(text: str) -> str:
    """Wrap text in a Speak tag using the globally selected voice (Plivo/Vobiz format)."""
    global CAMPAIGN_VOICE
    return f'<Speak language="hi-IN" voice="{CAMPAIGN_VOICE}">{text}</Speak>'

def sub_menu(base_url: str, key: str) -> str:
    """Sub-menu Gather block shown after a service explanation."""
    return f"""
    <GetDigits numDigits="1" timeout="10"
            action="{base_url}/ivr/handle_service/{key}" method="POST">
        {say("Meeting schedule करने के लिए 1 दबाएँ। और information के लिए 2 दबाएँ। अभी interested नहीं हैं तो 3 दबाएँ। Main menu पर वापस जाने के लिए 0 दबाएँ।")}
    </GetDigits>
    <Redirect method="POST">{base_url}/ivr/service/{key}</Redirect>"""

def main_menu(base_url: str) -> str:
    return f"""
<Response>
    <GetDigits numDigits="1" timeout="10"
            action="{base_url}/ivr/handle_menu" method="POST">
        {say("Software services जानने के लिए 1 दबाएँ। Digital marketing के लिए 2 दबाएँ। Logo designing के लिए 3 दबाएँ। Website design के लिए 4 दबाएँ।")}
    </GetDigits>
    {say("कोई response नहीं मिली। फिर से try कर रहे हैं।")}
    <Redirect method="POST">{base_url}/ivr/menu</Redirect>
</Response>"""

def parse_datetime_from_speech(speech: str) -> str:
    """Use Groq LLM to parse spoken date/time into YYYY-MM-DD HH:MM."""
    from datetime import timezone, timedelta
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

def parse_name_from_speech(speech: str) -> str:
    """Use Groq LLM to extract just the person's name from spoken text."""
    groq_client = Groq(api_key=os.getenv("IVR_GROQ_API_KEY"))
    prompt = (
        f"User said: '{speech}'. "
        f"Extract ONLY the person's name from this text. "
        f"For example, if they say 'mera naam rohit hai', return 'Rohit'. "
        f"If they say 'main rita bol rahi hoon', return 'Rita'. "
        f"Return ONLY the first name or full name, nothing else."
    )
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0.1,
        )
        name = response.choices[0].message.content.strip()
        # Clean up any quotes or extra punctuation
        return name.replace('"', '').replace("'", "")
    except Exception:
        return "Customer"

def send_meeting_sms(to_number: str, name: str, date_time_str: str, service_name: str):
    if not to_number: return
    try:
        client = Client(os.getenv("IVR_TWILIO_ACCOUNT_SID"), os.getenv("IVR_TWILIO_AUTH_TOKEN"))
        twilio_number = os.getenv("IVR_TWILIO_PHONE_NUMBER")
        msg = (f"Hello {name} ji,\n\n"
               f"Your meeting for {service_name} has been successfully scheduled.\n"
               f"Date & Time: {date_time_str}\n\n"
               f"We look forward to speaking with you.\n"
               f"- Binjwa IT Solutions")
        client.messages.create(body=msg, from_=twilio_number, to=to_number)
        print(f"✉️ SMS sent to {to_number}")
    except Exception as e:
        print(f"❌ SMS failed: {e}")

# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@router.post("/trigger_campaign")
async def trigger_campaign(request: Request):
    global CAMPAIGN_VOICE
    data = await request.json()
    
    # Update voice if provided by dashboard
    voice = data.get("voice")
    if voice:
        CAMPAIGN_VOICE = voice
        print(f"🎙️ Voice switched to: {CAMPAIGN_VOICE}")
        
    webhookId = data.get("webhookId", "")
    leads = data.get("leads", [])
    
    # Attach root webhookId to each lead if not present
    for lead in leads:
        if not lead.get("webhookId"):
            lead["webhookId"] = webhookId
            
    print(f"📥 Received {len(leads)} leads for campaign (webhookId: {webhookId}). Adding to queue...")
    campaign_queue.add_leads(leads)
    return {"status": "started", "queued": len(leads), "voice": CAMPAIGN_VOICE}

@router.post("/trigger_test_call")
async def trigger_test_call(request: Request):
    data = await request.json()
    phone = data.get("phone", "").strip()
    voice = data.get("voice", "Polly.Aditi")
    
    if not phone:
        return {"status": "error", "detail": "Phone number is required."}
        
    # Auto-format Indian numbers if they forgot +91
    if len(phone) == 10 and phone.isdigit():
        phone = f"+91{phone}"
    elif len(phone) == 12 and phone.startswith("91"):
        phone = f"+{phone}"
        
    base_url = os.getenv("IVR_BASE_URL")
    auth_id = os.getenv("IVR_VOBIZ_AUTH_ID")
    auth_token = os.getenv("IVR_VOBIZ_AUTH_TOKEN")
    vobiz_phone = os.getenv("IVR_VOBIZ_PHONE_NUMBER", "+911171366938")
    
    url = f"https://api.vobiz.ai/api/v1/Account/{auth_id}/Call/"
    payload = {
        "from": vobiz_phone,
        "to": phone,
        "answer_url": f"{base_url}/ivr/welcome_test?voice={voice}",
        "answer_method": "GET"
    }
    
    def make_call():
        res = requests.post(url, json=payload, headers={"X-Auth-ID": auth_id, "X-Auth-Token": auth_token, "Content-Type": "application/json"})
        if res.status_code not in [200, 201]:
            print(f"❌ Vobiz Error in Test Call: {res.status_code} - {res.text}")
        return res
        
    await asyncio.to_thread(make_call)
    print(f"📞 Triggered Sample Voice Call to {phone} using voice {voice}")
    return {"status": "started"}

@router.post("/trigger_single_call")
async def trigger_single_call(request: Request):
    """
    Dedicated endpoint to trigger a SINGLE IVR Call.
    """
    try:
        data = await request.json()
    except Exception:
        try:
            data = dict(await request.form())
        except Exception:
            return FastAPIResponse(content='{"status":"error","detail":"Invalid payload"}', status_code=400, media_type="application/json")
            
    global CAMPAIGN_VOICE
    
    phone = data.get("phone", data.get("phone_number", "")).strip()
    name = data.get("name", data.get("customer_name", "Customer"))
    voice = data.get("voice", "Polly.Aditi")
    webhookId = data.get("webhookId", "")
    
    # Set the global voice so the say() function uses it for this call
    CAMPAIGN_VOICE = voice
    
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
    
    url = f"https://api.vobiz.ai/api/v1/Account/{auth_id}/Call/"
    encoded_name = urllib.parse.quote(name)
    
    # Send request to the LIVE IVR Menu
    payload = {
        "from": vobiz_phone,
        "to": phone,
        "answer_url": f"{base_url}/ivr/welcome?name={encoded_name}&webhookId={webhookId}",
        "answer_method": "GET",
        "hangup_url": f"{base_url}/ivr/hangup?webhookId={webhookId}",
        "hangup_method": "POST"
    }
    
    def make_call():
        try:
            res = requests.post(url, json=payload, headers={"X-Auth-ID": auth_id, "X-Auth-Token": auth_token, "Content-Type": "application/json"}, timeout=10)
            return res
        except requests.exceptions.Timeout:
            print(f"⏱️ [VOBIZ] API call timed out for {phone}")
            return None
        except Exception as e:
            print(f"❌ [VOBIZ] API call failed: {e}")
            return None

    # Capture result to get CallUUID
    res = await asyncio.to_thread(make_call)
    
    if res is None:
        print(f"❌ [CAMPAIGN] Skipping {phone} — Vobiz API did not respond.")
        return JSONResponse({"status": "error", "message": "Vobiz API timeout or failure"}, status_code=503)
    
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
        "customer_phone": phone,
        "ivr_phone": vobiz_phone,
        "customer_name": name,
        "agent_type": "ivr_menu"
    }, webhookId)
    
    return {"status": "success", "message": f"Single call triggered successfully to {name}"}

@router.get("/preview_voice")
async def preview_voice(voice: str = "Polly.Aditi"):
    """
    Returns a raw WAV audio file generated by Murf API.
    This allows the web dashboard to play premium voices instantly online.
    """
    lang_code = "hi"
    gender = "female"
    voice_name = "अदिति"
    
    if voice == "Polly.Aditi":
        voice_name = "अदिति"
        lang_code = "hi"
    elif voice == "Polly.Raveena":
        voice_name = "Raveena"
        lang_code = "en"
    elif voice.lower() == "man":
        voice_name = "Ravi"
        lang_code = "en"
        gender = "male"
    elif voice.lower() == "woman":
        voice_name = "Anjali"
        lang_code = "hi"
        
    if lang_code == "en":
        text = f"Hello, I am {voice_name}, your personal AI assistant. Thank you for choosing Binjva IT Solutions."
    else:
        text = f"नमस्ते, मैं {voice_name} हूँ, आपका पर्सनल एआई असिस्टेंट। Binjva आई टी सोलूशन्स को चुनने के लिए धन्यवाद।"
        
    return StreamingResponse(generate_wav_stream(text, lang_code=lang_code, gender=gender), media_type="audio/wav")

@router.post("/hangup")
async def ivr_hangup(request: Request):
    """Triggered by Vobiz when the IVR call ends. Triggers the next queued call."""
    try:
        body = await request.json()
    except Exception:
        body = dict(await request.form())
    
    call_uuid = body.get("CallUUID", body.get("call_uuid", "unknown"))
    
    # Correctly identify IVR phone based on direction
    direction = body.get("Direction", body.get("direction", "")).lower()
    if direction == "outbound":
        ivr_phone = body.get("From", body.get("from", ""))
    else:
        ivr_phone = body.get("To", body.get("to", ""))
        
    if not ivr_phone:
        ivr_phone = os.getenv("IVR_VOBIZ_PHONE_NUMBER")
        
    webhookId = request.query_params.get("webhookId", "")
    print(f"📴 [IVR HANGUP] Call ended ({call_uuid}). Checking queue...")
    
    push_to_crm({
        "event_type": "call_disconnected",
        "call_uuid": call_uuid,
        "ivr_phone": ivr_phone,
        "customer_phone": customer_phone,
        "agent_type": "ivr_menu"
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


@router.get("/welcome")
@router.post("/welcome")
async def ivr_welcome(request: Request):
    base_url = os.getenv("IVR_BASE_URL", "")
    name = urllib.parse.unquote(request.query_params.get("name", "Customer"))
    encoded_name = urllib.parse.quote(name)
    
    # Get more details from Vobiz/Twilio
    body = await get_request_data(request)
            
    call_uuid = body.get("CallUUID", body.get("call_uuid", "unknown"))
    
    # Correctly identify customer and IVR phone based on direction
    direction = body.get("Direction", body.get("direction", "")).lower()
    if direction == "outbound":
        customer_phone = normalize_phone(body.get("To", body.get("to", "")))
        ivr_phone = normalize_phone(body.get("From", body.get("from", "")))
    else:
        customer_phone = normalize_phone(body.get("From", body.get("from", "")))
        ivr_phone = normalize_phone(body.get("To", body.get("to", "")))
        
    if not customer_phone:
        customer_phone = normalize_phone(body.get("From", body.get("To", "unknown")))
        ivr_phone = "unknown"
    
    webhookId = request.query_params.get("webhookId", "")
    
    # Send webhook
    push_to_crm({
        "event_type": "call_picked_up",
        "call_uuid": call_uuid,
        "customer_phone": customer_phone,
        "ivr_phone": ivr_phone,
        "customer_name": name,
        "agent_type": "ivr_menu"
    }, webhookId)
    
    prompt_text = f"Hello {name}, first of all congratulations for your new business! I am calling from बिंजवा IT Solutions. We provide complete solutions for your business from legal consultancy, compliance management, digital marketing, to website and app development. Meeting schedule करने के लिए 1 दबाएँ। हमारी sales team से बात करने মোহ 2 दबाएँ।"
    
    # Log the welcome prompt
    log_ivr_step(call_uuid, customer_phone, "IVR", prompt_text)
    
    xml = f"""
<Response>
    <GetDigits numDigits="1" timeout="10"
            action="{base_url}/ivr/handle_menu?name={encoded_name}&amp;webhookId={webhookId}" method="POST">
        {say(prompt_text)}
    </GetDigits>
    {say("कोई response नहीं मिली।")}
    <Redirect method="POST">{base_url}/ivr/welcome?name={encoded_name}&amp;webhookId={webhookId}</Redirect>
</Response>"""
    return xml_resp(xml)

@router.get("/welcome_test")
@router.post("/welcome_test")
async def ivr_welcome_test(request: Request):
    voice = request.query_params.get("voice", "Polly.Aditi")
    
    # Map voice code to readable name
    voice_name = "आपकी चुनी हुई"
    if voice == "Polly.Aditi":
        voice_name = "अदिति"
    elif voice == "Polly.Raveena":
        voice_name = "रवीना"
    elif voice.lower() == "man":
        voice_name = "मेल (Male)"
    elif voice.lower() == "woman":
        voice_name = "फीमेल (Female)"

    # Some platforms require MAN or WOMAN to be uppercase
    if voice.lower() in ["man", "woman"]:
        voice = voice.upper()
        
    return xml_resp(f"""
<Response>
    <Say language="hi-IN" voice="{voice}">नमस्ते! मैं {voice_name} हूँ। यह एक टेस्ट कॉल है। Binjva आई टी सोलूशन्स को चुनने के लिए धन्यवाद!</Say>
    <Hangup/>
</Response>""")


@router.post("/handle_menu")
async def ivr_handle_menu(request: Request):
    base_url = os.getenv("IVR_BASE_URL", "")
    # Support both Form (Twilio) and JSON (Vobiz)
    data = await get_request_data(request)
    
    digit = str(data.get("Digits", data.get("digits", ""))).strip()
    if digit:
        digit = digit[0] # Handle DTMF bounce (e.g. '11' -> '1')
    name = urllib.parse.unquote(request.query_params.get("name", "Customer"))
    encoded_name = urllib.parse.quote(name)

    direction = data.get("Direction", data.get("direction", "")).lower()
    if direction == "outbound":
        phone_number = normalize_phone(data.get("To", data.get("to", "")))
        ivr_phone = normalize_phone(data.get("From", data.get("from", "")))
    else:
        phone_number = normalize_phone(data.get("From", data.get("from", "")))
        ivr_phone = normalize_phone(data.get("To", data.get("to", "")))
        
    if not ivr_phone:
        ivr_phone = normalize_phone(os.getenv("IVR_VOBIZ_PHONE_NUMBER", ""))
        
    call_uuid = data.get("CallUUID", data.get("call_uuid", ""))
    webhookId = request.query_params.get("webhookId", "")

    if digit == "1":
        log_ivr_step(call_uuid, phone_number, "Customer", "Pressed 1 (Interested)")
        
        push_to_crm({
            "event_type": "lead_tag",
            "call_uuid": call_uuid,
            "customer_phone": phone_number,
            "ivr_phone": ivr_phone,
            "customer_name": name,
            "tag": "Interested",
            "key_pressed": "1"
        }, webhookId)
        
        prompt_text = f"बहुत बढ़िया {name} जी। कृपया बताएँ कि आप किस दिन और कितने बजे मीटिंग करना चाहते हैं?"
        log_ivr_step(call_uuid, phone_number, "IVR", prompt_text)
        
        return xml_resp(f"""<Response>
    {say(prompt_text)}
    <Record action="{base_url}/ivr/confirm/1?name={encoded_name}&amp;webhookId={webhookId}" method="POST" maxLength="8" timeout="1" playBeep="true" />
    <Redirect method="POST">{base_url}/ivr/fallback_time/1?name={encoded_name}&amp;webhookId={webhookId}</Redirect>
</Response>""")
    elif digit == "2":
        log_ivr_step(call_uuid, phone_number, "Customer", "Pressed 2 (Wants to Talk to Sales Team)")
        
        push_to_crm({
            "event_type": "lead_tag",
            "call_uuid": call_uuid,
            "customer_phone": phone_number,
            "ivr_phone": ivr_phone,
            "customer_name": name,
            "tag": "Wants to Talk to Sales Team",
            "key_pressed": "2"
        }, webhookId)
        
        forward_prompt = "ठीक है, हम आपकी कॉल हमारी sales team को ट्रांसफर कर रहे हैं। कृपया लाइन पर बने रहें।"
        log_ivr_step(call_uuid, phone_number, "IVR", forward_prompt)
        log_ivr_step(call_uuid, phone_number, "System", "Call Forwarded to Sales Team (+919302565968). Call completed.")
        
        full_transcript = get_ivr_transcript(call_uuid, phone_number)
        summary = summarize_ivr_call(full_transcript)
        
        # Also push a call_summary event for Sales Team Request!
        push_to_crm({
            "event_type": "call_summary",
            "call_uuid": call_uuid,
            "customer_phone": phone_number,
            "ivr_phone": ivr_phone,
            "customer_name": name,
            "final_status": "Sales Team Requested",
            "prompt_text": full_transcript,
            "prompt": full_transcript,
            "transcript": full_transcript,
            "summary": summary
        }, webhookId)

        auth_id = os.getenv("IVR_VOBIZ_AUTH_ID")
        auth_token = os.getenv("IVR_VOBIZ_AUTH_TOKEN")
        
        # Fire API call asynchronously to transfer
        def trigger_transfer():
            transfer_url = f"{base_url}/ivr/transfer_xml?number=+918827614849&callerId={ivr_phone}"
            api_url = f"https://api.vobiz.ai/api/v1/Account/{auth_id}/Call/{call_uuid}/"
            print(f"🔄 Triggering Vobiz Transfer API: {api_url} to +918827614849 with callerId {ivr_phone}")
            try:
                import requests
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

        return xml_resp(f"""<Response>
    {say(forward_prompt)}
    <Pause length="10"/>
</Response>""")
    else:
        invalid_text = "Invalid option. कृपया 1 या 2 दबाएँ।"
        log_ivr_step(call_uuid, phone_number, "Customer", f"Pressed invalid key: {digit}")
        log_ivr_step(call_uuid, phone_number, "IVR", invalid_text)
        
        action_url = f"{base_url}/ivr/handle_menu?name={encoded_name}&amp;webhookId={webhookId}"
        return xml_resp(f"""<Response>
    <GetDigits numDigits="1" timeout="10" action="{action_url}" method="POST">
        {say(invalid_text)}
    </GetDigits>
    {say(invalid_text)}
    <Redirect method="POST">{base_url}/ivr/welcome?name={encoded_name}&amp;webhookId={webhookId}</Redirect>
</Response>""")


@router.get("/service/{key}")
@router.post("/service/{key}")
async def ivr_service(key: str, request: Request):
    base_url = os.getenv("IVR_BASE_URL", "")
    service = IVR_SERVICES.get(key)
    if not service:
        return xml_resp(f"""<Response><Redirect method="POST">{base_url}/ivr/menu</Redirect></Response>""")
    return xml_resp(f"""<Response>
    {say(service["short"])}
    <Wait length="1"/>
    {sub_menu(base_url, key)}
</Response>""")


@router.post("/handle_service/{key}")
async def ivr_handle_service(key: str, request: Request):
    base_url = os.getenv("IVR_BASE_URL", "")
    data = await get_request_data(request)
    
    digit = str(data.get("Digits", data.get("digits", ""))).strip()
    if digit:
        digit = digit[0] # Handle DTMF bounce (e.g. '11' -> '1')
    
    direction = data.get("Direction", data.get("direction", "")).lower()
    if direction == "outbound":
        phone_number = normalize_phone(data.get("To", data.get("to", "")))
        ivr_phone = normalize_phone(data.get("From", data.get("from", "")))
    else:
        phone_number = normalize_phone(data.get("From", data.get("from", "")))
        ivr_phone = normalize_phone(data.get("To", data.get("to", "")))
        
    if not ivr_phone:
        ivr_phone = normalize_phone(os.getenv("IVR_VOBIZ_PHONE_NUMBER", ""))
        
    call_uuid = data.get("CallUUID", data.get("call_uuid", ""))
    webhookId = request.query_params.get("webhookId", "")
    
    # name is not passed directly to handle_service in the url, so we use "Customer" as default
    # If name is needed, we should add it to the handle_service URL
    
    if digit == "1":
        push_to_crm({
            "event_type": "lead_tag",
            "call_uuid": call_uuid,
            "customer_phone": phone_number,
            "ivr_phone": ivr_phone,
            "customer_name": "Customer",
            "tag": "Interested in Meeting",
            "key_pressed": "1"
        }, webhookId)
        return xml_resp(f"""<Response><Redirect method="POST">{base_url}/ivr/book/{key}?webhookId={webhookId}</Redirect></Response>""")
    elif digit == "2":
        push_to_crm({
            "event_type": "lead_tag",
            "call_uuid": call_uuid,
            "customer_phone": phone_number,
            "ivr_phone": ivr_phone,
            "customer_name": "Customer",
            "tag": "Needs More Info",
            "key_pressed": "2"
        }, webhookId)
        return xml_resp(f"""<Response><Redirect method="POST">{base_url}/ivr/more/{key}?webhookId={webhookId}</Redirect></Response>""")
    elif digit == "3":
        push_to_crm({
            "event_type": "lead_tag",
            "call_uuid": call_uuid,
            "customer_phone": phone_number,
            "ivr_phone": ivr_phone,
            "customer_name": "Customer",
            "tag": "Not Interested",
            "key_pressed": "3"
        }, webhookId)
        return xml_resp(f"""<Response><Redirect method="POST">{base_url}/ivr/goodbye?webhookId={webhookId}</Redirect></Response>""")
    elif digit == "0":
        return xml_resp(f"""<Response>
    {say("Main menu पर वापस आ रहे हैं।")}
    <Redirect method="POST">{base_url}/ivr/menu?webhookId={webhookId}</Redirect>
</Response>""")
    return xml_resp(f"""<Response>
    {say("Invalid option। कृपया 0 से 3 के बीच कोई number दबाएँ।")}
    <Redirect method="POST">{base_url}/ivr/service/{key}?webhookId={webhookId}</Redirect>
</Response>""")


@router.get("/more/{key}")
@router.post("/more/{key}")
async def ivr_more(key: str, request: Request):
    base_url = os.getenv("IVR_BASE_URL", "")
    service = IVR_SERVICES.get(key)
    if not service:
        return xml_resp(f"""<Response><Redirect method="POST">{base_url}/ivr/menu</Redirect></Response>""")
    return xml_resp(f"""<Response>
    {say(service["detail"])}
    <Wait length="1"/>
    {sub_menu(base_url, key)}
</Response>""")


@router.get("/book/{key}")
@router.post("/book/{key}")
async def ivr_book(key: str, request: Request):
    base_url = os.getenv("IVR_BASE_URL", "")
    service = IVR_SERVICES.get(key, {})
    service_name = service.get("name", "IT Service")
    is_retry = request.query_params.get("retry", "")

    prompt = "माफ़ कीजिए, मुझे सुनाई नहीं दिया, क्या आप अपना नाम रिपीट कर सकते हैं?" if is_retry else f"{service_name} के लिए मीटिंग बुक करने के लिए, कृपया अपना पूरा नाम बताएँ।"
    webhookId = request.query_params.get("webhookId", "")

    return xml_resp(f"""<Response>
    {say(prompt)}
    <Record action="{base_url}/ivr/book_time/{key}?webhookId={webhookId}" method="POST" maxLength="6" timeout="1" playBeep="true" />
    <Redirect method="POST">{base_url}/ivr/book/{key}?retry=1&amp;webhookId={webhookId}</Redirect>
</Response>""")


@router.post("/book_time/{key}")
async def ivr_book_time(key: str, request: Request):
    base_url = os.getenv("IVR_BASE_URL", "")
    webhookId = request.query_params.get("webhookId", "")
    data = await get_request_data(request)
    
    print(f"🎙️ [RECORD DATA book_time]: {data}")
    
    # Check for RecordUrl or RecordingUrl or RecordFile
    record_url = data.get("RecordFile", data.get("RecordUrl", data.get("RecordingUrl", "")))
    
    if record_url:
        speech = transcribe_audio_url(record_url)
    else:
        speech = data.get("SpeechResult", data.get("speech_result", "")).strip()
    
    if not speech:
        return xml_resp(f"""<Response><Redirect method="POST">{base_url}/ivr/book/{key}?retry=1&amp;webhookId={webhookId}</Redirect></Response>""")

    name = parse_name_from_speech(speech)
    encoded_name = urllib.parse.quote(name)
    return xml_resp(f"""<Response>
    {say(f"शुक्रिया {name} जी। आप सोमवार से शुक्रवार के बीच किसी भी दिन मीटिंग शेड्यूल करवा सकते हैं।")}
    {say("कृपया बताएँ कि आप किस दिन और कितने बजे मीटिंग करना चाहते हैं?")}
    <Record action="{base_url}/ivr/confirm/{key}?name={encoded_name}&amp;webhookId={webhookId}" method="POST" maxLength="8" timeout="1" playBeep="true" />
    <Redirect method="POST">{base_url}/ivr/fallback_time/{key}?name={encoded_name}&amp;webhookId={webhookId}</Redirect>
</Response>""")

@router.post("/fallback_time/{key}")
async def ivr_fallback_time(key: str, request: Request):
    base_url = os.getenv("IVR_BASE_URL", "")
    name = urllib.parse.unquote(request.query_params.get("name", "Customer"))
    encoded_name = urllib.parse.quote(name)
    retry = int(request.query_params.get("retry", "0"))
    webhookId = request.query_params.get("webhookId", "")
    conflict = request.query_params.get("conflict", "")

    data = await get_request_data(request)
    call_uuid = data.get("CallUUID", data.get("call_uuid", ""))
    
    direction = data.get("Direction", data.get("direction", "")).lower()
    if direction == "outbound":
        phone_number = normalize_phone(data.get("To", data.get("to", "")))
    else:
        phone_number = normalize_phone(data.get("From", data.get("from", "")))

    # After 2 failed retries, give up gracefully
    if retry >= 2:
        goodbye_prompt = f"कोई बात नहीं {name} जी। आप बाद में हमें call कर सकते हैं। Binjva IT Solutions को समय देने के लिए बहुत धन्यवाद। आपका दिन शुभ हो।"
        log_ivr_step(call_uuid, phone_number, "IVR", goodbye_prompt)
        return xml_resp(f"""<Response>
    {say(goodbye_prompt)}
    <Hangup/>
</Response>""")

    if conflict:
        prompt = "कृपया सोमवार से शुक्रवार के बीच कोई दूसरा दिन या समय बताएँ जब आप मीटिंग करना चाहते हैं।"
    else:
        prompt = "माफ़ कीजिए, मुझे सुनाई नहीं दिया, क्या आप रिपीट कर सकते हैं कि आप सोमवार से शुक्रवार के बीच किस दिन और कितने बजे मीटिंग करना चाहते हैं?"

    log_ivr_step(call_uuid, phone_number, "IVR", prompt)

    return xml_resp(f"""<Response>
    {say(prompt)}
    <Record action="{base_url}/ivr/confirm/{key}?name={encoded_name}&amp;webhookId={webhookId}" method="POST" maxLength="8" timeout="1" playBeep="true" />
    <Redirect method="POST">{base_url}/ivr/fallback_time/{key}?name={encoded_name}&amp;retry={retry + 1}&amp;webhookId={webhookId}</Redirect>
</Response>""")


@router.post("/confirm/{key}")
async def ivr_confirm(key: str, request: Request):
    base_url = os.getenv("IVR_BASE_URL", "")
    data = await get_request_data(request)
    
    print(f"🎙️ [RECORD DATA confirm]: {data}")
    
    record_url = data.get("RecordFile", data.get("RecordUrl", data.get("RecordingUrl", "")))
    if record_url:
        time_speech = await asyncio.to_thread(transcribe_audio_url, record_url)
    else:
        time_speech = data.get("SpeechResult", data.get("speech_result", "")).strip()
        
    call_uuid = data.get("CallUUID", data.get("call_uuid", ""))

    direction = data.get("Direction", data.get("direction", "")).lower()
    if direction == "outbound":
        raw_phone = data.get("To", data.get("to", ""))
    else:
        raw_phone = data.get("From", data.get("from", ""))
        
    # Twilio requires proper E.164 formatting (e.g. +91...)
    phone_number = raw_phone.strip()
    if not phone_number.startswith("+"):
        phone_number = f"+{phone_number}"

    name = urllib.parse.unquote(request.query_params.get("name", "Customer"))
    webhookId = request.query_params.get("webhookId", "")
    service = IVR_SERVICES.get(key, {})
    service_name = service.get("name", "IT Service")

    if not time_speech:
        log_ivr_step(call_uuid, phone_number, "Customer (Voice)", "[No speech detected]")
        encoded_name = urllib.parse.quote(name)
        return xml_resp(f"""<Response><Redirect method="POST">{base_url}/ivr/fallback_time/{key}?name={encoded_name}&amp;webhookId={webhookId}</Redirect></Response>""")
        
    log_ivr_step(call_uuid, phone_number, "Customer (Voice)", time_speech)

    dt_str = await asyncio.to_thread(parse_datetime_from_speech, time_speech)

    if dt_str == "MISSING" or not dt_str:
        log_ivr_step(call_uuid, phone_number, "System Parsed", f"Failed to parse time from speech: '{time_speech}'")
        encoded_name = urllib.parse.quote(name)
        return xml_resp(f"""<Response><Redirect method="POST">{base_url}/ivr/fallback_time/{key}?name={encoded_name}&amp;webhookId={webhookId}</Redirect></Response>""")

    # Check calendar availability right now before completing
    from calendar_api import get_calendar_service
    try:
        service = get_calendar_service()
        from datetime import timezone, timedelta
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
            encoded_name = urllib.parse.quote(name)
            return xml_resp(f"""<Response>
    {say("माफ़ कीजिए, उस समय पर हमारी एक और मीटिंग शेड्यूल है।")}
    <Redirect method="POST">{base_url}/ivr/fallback_time/{key}?name={encoded_name}&amp;webhookId={webhookId}&amp;conflict=1</Redirect>
</Response>""")
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
            
            call_uuid = data.get("CallUUID", data.get("call_uuid", ""))
            if result != "ERROR_ALREADY_BOOKED":
                log_ivr_step(call_uuid, phone_number, "System Parsed", f"Scheduled on {friendly_time}")
                
                full_transcript = get_ivr_transcript(call_uuid, phone_number)
                summary = summarize_ivr_call(full_transcript)
                
                push_to_crm({
                    "event_type": "call_summary",
                    "call_uuid": call_uuid,
                    "customer_phone": phone_number,
                    "ivr_phone": os.getenv("IVR_VOBIZ_PHONE_NUMBER"),
                    "customer_name": name,
                    "final_status": "Meeting Booked",
                    "meeting_time": friendly_time,
                    "prompt_text": full_transcript,
                    "prompt": full_transcript,
                    "transcript": full_transcript,
                    "summary": summary
                }, webhookId)
            # Temporarily disabled SMS per user request
            # if result != "ERROR_ALREADY_BOOKED":
            #     await asyncio.to_thread(send_meeting_sms, phone_number, name, friendly_time, service_name)
        except Exception as e:
            print(f"❌ Background booking error: {e}")

    asyncio.create_task(finalize_booking())

    goodbye_prompt_1 = f"बहुत अच्छा! {name} जी, हमने आपकी {friendly_time} की request ले ली है।"
    goodbye_prompt_2 = "हमारी team जल्द ही calendar check करके आपको SMS भेज देगी। Binjva IT Solutions को समय देने के लिए धन्यवाद!"
    log_ivr_step(call_uuid, phone_number, "IVR", f"{goodbye_prompt_1} {goodbye_prompt_2}")

    return xml_resp(f"""
<Response>
    {say(goodbye_prompt_1)}
    {say(goodbye_prompt_2)}
    <Hangup/>
</Response>""")


@router.get("/goodbye")
@router.post("/goodbye")
async def ivr_goodbye(request: Request):
    return xml_resp(f"""
<Response>
    {say("कोई बात नहीं। जब भी ज़रूरत हो, हमें call करें। Binjva IT Solutions आपकी service में हमेशा तैयार है। धन्यवाद! नमस्ते!")}
    <Hangup/>
</Response>""")

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
