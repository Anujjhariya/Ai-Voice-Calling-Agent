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
from fastapi import APIRouter, Request
from fastapi.responses import Response as FastAPIResponse
from twilio.rest import Client
from groq import Groq
from dotenv import load_dotenv
from calendar_api import book_meeting
from outbound_vobiz_ivr import make_vobiz_ivr_call

load_dotenv()

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

# ─────────────────────────────────────────────
# CAMPAIGN QUEUE
# ─────────────────────────────────────────────
class CampaignQueue:
    def __init__(self):
        self.leads = []
        self.is_running = False

    def add_leads(self, new_leads):
        self.leads.extend(new_leads)
        if not self.is_running and self.leads:
            self.trigger_next()

    def trigger_next(self):
        if self.leads:
            self.is_running = True
            lead = self.leads.pop(0)
            name = lead.get("name", "Customer")
            phone = lead.get("phone", "")
            print(f"\n🚀 [CAMPAIGN QUEUE] Dialing {name} at {phone}... ({len(self.leads)} remaining)\n")
            try:
                make_vobiz_ivr_call(phone, name)
            except Exception as e:
                print(f"❌ Failed to dial {name}: {e}")
                self.trigger_next() # skip and continue
        else:
            self.is_running = False
            print("\n🎉 [CAMPAIGN QUEUE] All calls finished!\n")

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
    print(f"\n📡 [IVR XML RESPONSE]:\n{xml_body}\n")
    return FastAPIResponse(content=xml_body, media_type="text/xml")

def transcribe_audio_url(url: str) -> str:
    """Download audio from Vobiz and transcribe using Groq Whisper."""
    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    try:
        print(f"⏳ Downloading audio for transcription: {url}")
        headers = {
            "X-Auth-ID": os.getenv("VOBIZ_AUTH_ID", ""),
            "X-Auth-Token": os.getenv("VOBIZ_AUTH_TOKEN", "")
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
    """Wrap text in a Speak tag with Amazon Polly Aditi voice (Bilingual Hindi/English)."""
    return f'<Speak language="hi-IN" voice="Polly.Aditi">{text}</Speak>'

def sub_menu(base_url: str, key: str) -> str:
    """Sub-menu Gather block shown after a service explanation."""
    return f"""
    <GetDigits numDigits="1" timeout="10"
            action="{base_url}/ivr/handle_service/{key}" method="POST">
        {say("Meeting schedule करने के लिए 1 दबाएँ।")}
        {say("और information के लिए 2 दबाएँ।")}
        {say("अभी interested नहीं हैं तो 3 दबाएँ।")}
        {say("Main menu पर वापस जाने के लिए 0 दबाएँ।")}
    </GetDigits>
    <Redirect method="POST">{base_url}/ivr/service/{key}</Redirect>"""

def main_menu(base_url: str) -> str:
    return f"""
<Response>
    <GetDigits numDigits="1" timeout="10"
            action="{base_url}/ivr/handle_menu" method="POST">
        {say("Software services जानने के लिए 1 दबाएँ।")}
        {say("Digital marketing के लिए 2 दबाएँ।")}
        {say("Logo designing के लिए 3 दबाएँ।")}
        {say("Website design के लिए 4 दबाएँ।")}
    </GetDigits>
    {say("कोई response नहीं मिली। फिर से try कर रहे हैं।")}
    <Redirect method="POST">{base_url}/ivr/menu</Redirect>
</Response>"""

def parse_datetime_from_speech(speech: str) -> str:
    """Use Groq LLM to parse spoken date/time into YYYY-MM-DD HH:MM."""
    now = datetime.now()
    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    prompt = (
        f"Today is {now.strftime('%Y-%m-%d')} ({now.strftime('%A')}). "
        f"User said in Hindi/Hinglish: '{speech}'. "
        f"IMPORTANT Hindi time words: "
        f"'subah/savere' = morning = AM (e.g. subah 10 baje = 10:00), "
        f"'dopahar' = afternoon = 12:00-15:00, "
        f"'sham/shaam' = evening = PM (e.g. sham 3 baje = 15:00), "
        f"'raat' = night = PM (e.g. raat 8 baje = 20:00). "
        f"Extract the meeting date and time. Return ONLY format 'YYYY-MM-DD HH:MM' (24-hour). "
        f"Business hours: 08:00 to 20:00. "
        f"If no time word, default to 10:00. "
        f"Return ONLY the datetime string, nothing else."
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
    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
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
        client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
        twilio_number = os.getenv("TWILIO_PHONE_NUMBER")
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
    data = await request.json()
    leads = data.get("leads", [])
    print(f"📥 Received {len(leads)} leads for campaign. Adding to queue...")
    campaign_queue.add_leads(leads)
    return {"status": "started", "queued": len(leads)}

@router.post("/hangup")
async def ivr_hangup(request: Request):
    """Triggered by Vobiz when the IVR call ends. Triggers the next queued call."""
    try:
        body = await request.json()
    except Exception:
        body = dict(await request.form())
    
    print(f"📴 [IVR HANGUP] Call ended. Checking queue...")
    
    # Wait 2 seconds before dialing the next one to ensure the channel is fully released
    async def delayed_next():
        await asyncio.sleep(2)
        campaign_queue.trigger_next()
        
    asyncio.create_task(delayed_next())
    return {"status": "ok"}


@router.get("/welcome")
@router.post("/welcome")
async def ivr_welcome(request: Request):
    base_url = os.getenv("BASE_URL", "")
    name = urllib.parse.unquote(request.query_params.get("name", "Customer"))
    encoded_name = urllib.parse.quote(name)
    xml = f"""
<Response>
    <GetDigits numDigits="1" timeout="10"
            action="{base_url}/ivr/handle_menu?name={encoded_name}" method="POST">
        {say(f"Hello {name}, first of all congratulations for your new business! I am calling from Binjwa IT Solutions.")}
        {say("We provide complete solutions for your business from legal consultancy, compliance management, digital marketing, to website and app development.")}
        {say("Meeting schedule करने के लिए 1 दबाएँ। Not interested हैं तो 2 दबाएँ।")}
    </GetDigits>
    {say("कोई response नहीं मिली।")}
    <Redirect method="POST">{base_url}/ivr/welcome?name={encoded_name}</Redirect>
</Response>"""
    return xml_resp(xml)


@router.post("/handle_menu")
async def ivr_handle_menu(request: Request):
    base_url = os.getenv("BASE_URL", "")
    # Support both Form (Twilio) and JSON (Vobiz)
    try:
        data = await request.json()
    except Exception:
        data = dict(await request.form())
    
    digit = data.get("Digits", data.get("digits", "")).strip()
    name = urllib.parse.unquote(request.query_params.get("name", "Customer"))
    encoded_name = urllib.parse.quote(name)

    if digit == "1":
        return xml_resp(f"""<Response>
    {say(f"बहुत बढ़िया {name} जी। कृपया बताएँ कि आप किस दिन और कितने बजे मीटिंग करना चाहते हैं?")}
    <Record action="{base_url}/ivr/confirm/1?name={encoded_name}" method="POST" maxLength="15" timeout="2" playBeep="true" />
    <Redirect method="POST">{base_url}/ivr/fallback_time/1?name={encoded_name}</Redirect>
</Response>""")
    elif digit == "2":
        return xml_resp(f"""<Response>
    {say("कोई बात नहीं। Binjwa IT Solutions को समय देने के लिए धन्यवाद। आपका दिन शुभ हो।")}
    <Hangup/>
</Response>""")
    else:
        return xml_resp(f"""<Response>
    {say("Invalid option। कृपया 1 या 2 दबाएँ।")}
    <Redirect method="POST">{base_url}/ivr/welcome?name={encoded_name}</Redirect>
</Response>""")


@router.get("/service/{key}")
@router.post("/service/{key}")
async def ivr_service(key: str, request: Request):
    base_url = os.getenv("BASE_URL", "")
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
    base_url = os.getenv("BASE_URL", "")
    try:
        data = await request.json()
    except Exception:
        data = dict(await request.form())
    
    digit = data.get("Digits", data.get("digits", "")).strip()
    if digit == "1":
        return xml_resp(f"""<Response><Redirect method="POST">{base_url}/ivr/book/{key}</Redirect></Response>""")
    elif digit == "2":
        return xml_resp(f"""<Response><Redirect method="POST">{base_url}/ivr/more/{key}</Redirect></Response>""")
    elif digit == "3":
        return xml_resp(f"""<Response><Redirect method="POST">{base_url}/ivr/goodbye</Redirect></Response>""")
    elif digit == "0":
        return xml_resp(f"""<Response>
    {say("Main menu पर वापस आ रहे हैं।")}
    <Redirect method="POST">{base_url}/ivr/menu</Redirect>
</Response>""")
    return xml_resp(f"""<Response>
    {say("Invalid option। कृपया 0 से 3 के बीच कोई number दबाएँ।")}
    <Redirect method="POST">{base_url}/ivr/service/{key}</Redirect>
</Response>""")


@router.get("/more/{key}")
@router.post("/more/{key}")
async def ivr_more(key: str, request: Request):
    base_url = os.getenv("BASE_URL", "")
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
    base_url = os.getenv("BASE_URL", "")
    service = IVR_SERVICES.get(key, {})
    service_name = service.get("name", "IT Service")
    is_retry = request.query_params.get("retry", "")

    prompt = "माफ़ कीजिए, मुझे सुनाई नहीं दिया, क्या आप अपना नाम रिपीट कर सकते हैं?" if is_retry else f"{service_name} के लिए मीटिंग बुक करने के लिए, कृपया अपना पूरा नाम बताएँ।"

    return xml_resp(f"""<Response>
    {say(prompt)}
    <Record action="{base_url}/ivr/book_time/{key}" method="POST" maxLength="10" timeout="2" playBeep="true" />
    <Redirect method="POST">{base_url}/ivr/book/{key}?retry=1</Redirect>
</Response>""")


@router.post("/book_time/{key}")
async def ivr_book_time(key: str, request: Request):
    base_url = os.getenv("BASE_URL", "")
    try:
        data = await request.json()
    except Exception:
        data = dict(await request.form())
    
    print(f"🎙️ [RECORD DATA book_time]: {data}")
    
    # Check for RecordUrl or RecordingUrl or RecordFile
    record_url = data.get("RecordFile", data.get("RecordUrl", data.get("RecordingUrl", "")))
    
    if record_url:
        speech = transcribe_audio_url(record_url)
    else:
        speech = data.get("SpeechResult", data.get("speech_result", "")).strip()
    
    if not speech:
        return xml_resp(f"""<Response><Redirect method="POST">{base_url}/ivr/book/{key}?retry=1</Redirect></Response>""")

    name = parse_name_from_speech(speech)
    encoded_name = urllib.parse.quote(name)
    return xml_resp(f"""<Response>
    {say(f"शुक्रिया {name} जी। आप सोमवार से शुक्रवार के बीच किसी भी दिन मीटिंग शेड्यूल करवा सकते हैं।")}
    {say("कृपया बताएँ कि आप किस दिन और कितने बजे मीटिंग करना चाहते हैं?")}
    <Record action="{base_url}/ivr/confirm/{key}?name={encoded_name}" method="POST" maxLength="15" timeout="2" playBeep="true" />
    <Redirect method="POST">{base_url}/ivr/fallback_time/{key}?name={encoded_name}</Redirect>
</Response>""")

@router.post("/fallback_time/{key}")
async def ivr_fallback_time(key: str, request: Request):
    base_url = os.getenv("BASE_URL", "")
    name = urllib.parse.unquote(request.query_params.get("name", "Customer"))
    encoded_name = urllib.parse.quote(name)
    return xml_resp(f"""<Response>
    {say("माफ़ कीजिए, मुझे सुनाई नहीं दिया, क्या आप रिपीट कर सकते हैं कि आप सोमवार से शुक्रवार के बीच किस दिन और कितने बजे मीटिंग करना चाहते हैं?")}
    <Record action="{base_url}/ivr/confirm/{key}?name={encoded_name}" method="POST" maxLength="15" timeout="2" playBeep="true" />
    <Redirect method="POST">{base_url}/ivr/fallback_time/{key}?name={encoded_name}</Redirect>
</Response>""")


@router.post("/confirm/{key}")
async def ivr_confirm(key: str, request: Request):
    base_url = os.getenv("BASE_URL", "")
    try:
        data = await request.json()
    except Exception:
        data = dict(await request.form())
    
    print(f"🎙️ [RECORD DATA confirm]: {data}")
    
    record_url = data.get("RecordFile", data.get("RecordUrl", data.get("RecordingUrl", "")))
    if record_url:
        time_speech = await asyncio.to_thread(transcribe_audio_url, record_url)
    else:
        time_speech = data.get("SpeechResult", data.get("speech_result", "")).strip()

    phone_number = data.get("From", data.get("from", ""))
    name = urllib.parse.unquote(request.query_params.get("name", "Customer"))
    service = IVR_SERVICES.get(key, {})
    service_name = service.get("name", "IT Service")

    if not time_speech:
        encoded_name = urllib.parse.quote(name)
        return xml_resp(f"""<Response><Redirect method="POST">{base_url}/ivr/fallback_time/{key}?name={encoded_name}</Redirect></Response>""")
        
    dt_str = await asyncio.to_thread(parse_datetime_from_speech, time_speech)

    try:
        friendly_time = datetime.strptime(dt_str, "%Y-%m-%d %H:%M").strftime("%d %B %Y at %I:%M %p")
    except Exception:
        friendly_time = dt_str

    async def finalize_booking():
        try:
            result = await asyncio.to_thread(book_meeting, name, dt_str)
            print(f"📅 Background Booking: {name} | {dt_str} | {result}")
            if result != "ERROR_ALREADY_BOOKED":
                await asyncio.to_thread(send_meeting_sms, phone_number, name, friendly_time, service_name)
        except Exception as e:
            print(f"❌ Background booking error: {e}")

    asyncio.create_task(finalize_booking())

    return xml_resp(f"""
<Response>
    {say(f"बहुत अच्छा! {name} जी, हमने आपकी {friendly_time} की request ले ली है।")}
    {say("हमारी team जल्द ही calendar check करके आपको SMS भेज देगी। Binjwa IT Solutions को समय देने के लिए धन्यवाद!")}
    <Hangup/>
</Response>""")


@router.get("/goodbye")
@router.post("/goodbye")
async def ivr_goodbye(request: Request):
    return xml_resp(f"""
<Response>
    {say("कोई बात नहीं। जब भी ज़रूरत हो, हमें call करें। Binjwa IT Solutions आपकी service में हमेशा तैयार है। धन्यवाद! नमस्ते!")}
    <Hangup/>
</Response>""")
