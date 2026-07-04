"""
ivr_server.py
-------------
Standalone IVR (Interactive Voice Response) System for Binjwa IT Solutions.
NO AI Agent involved — pure Twilio TwiML menu system.

Run this on a SEPARATE port:
    uvicorn ivr_server:ivr_app --host 0.0.0.0 --port 8001 --reload

IVR Menu:
  1 → Website / App Development  (info + callback request)
  2 → Digital Marketing          (info + callback request)
  3 → Pricing & Quotation        (info + callback request)
  4 → Schedule a Meeting         (collects callback request)
  0 → Transfer to human agent    (Dial your number)
"""

import os
from fastapi import FastAPI, Form
from fastapi.responses import Response
from dotenv import load_dotenv

load_dotenv()

ivr_app = FastAPI()

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────
BASE_URL      = os.getenv("BASE_URL", "")
HUMAN_NUMBER  = os.getenv("HUMAN_PHONE_NUMBER", "+918319688692")

def twiml(xml: str) -> Response:
    return Response(content=xml.strip(), media_type="application/xml")

# ─────────────────────────────────────────────
# ROOT MENU
# ─────────────────────────────────────────────
@ivr_app.get("/ivr")
@ivr_app.post("/ivr")
async def main_menu():
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather numDigits="1" action="{BASE_URL}/ivr/handle" method="POST" timeout="10">
        <Say language="hi-IN" voice="Polly.Aditi">
            नमस्कार! Binjwa IT Solutions में आपका स्वागत है।
            कृपया ध्यान से सुनें और अपना option चुनें।
            Website या App Development के लिए 1 दबाएं।
            Digital Marketing के लिए 2 दबाएं।
            Pricing और Quotation के लिए 3 दबाएं।
            Meeting Schedule करने के लिए 4 दबाएं।
            हमारी team से directly बात करने के लिए 0 दबाएं।
        </Say>
    </Gather>
    <Say language="hi-IN" voice="Polly.Aditi">
        कोई input नहीं मिली। कृपया दोबारा call करें। धन्यवाद!
    </Say>
</Response>"""
    return twiml(xml)


# ─────────────────────────────────────────────
# HANDLE MAIN MENU KEYPRESS
# ─────────────────────────────────────────────
@ivr_app.post("/ivr/handle")
async def handle_menu(Digits: str = Form(default="")):
    digit = Digits.strip()
    print(f"📞 IVR Keypress: [{digit}]")

    routes = {
        "1": f"{BASE_URL}/ivr/web-app",
        "2": f"{BASE_URL}/ivr/marketing",
        "3": f"{BASE_URL}/ivr/pricing",
        "4": f"{BASE_URL}/ivr/meeting",
        "0": f"{BASE_URL}/ivr/human",
    }

    if digit in routes:
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Redirect method="POST">{routes[digit]}</Redirect>
</Response>"""
    else:
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="hi-IN" voice="Polly.Aditi">
        माफ़ कीजिये, यह option valid नहीं है। कृपया दोबारा try करें।
    </Say>
    <Redirect method="POST">{BASE_URL}/ivr</Redirect>
</Response>"""
    return twiml(xml)


# ─────────────────────────────────────────────
# OPTION 1: Website / App Development
# ─────────────────────────────────────────────
@ivr_app.post("/ivr/web-app")
async def web_app():
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather numDigits="1" action="{BASE_URL}/ivr/web-app/handle" method="POST" timeout="8">
        <Say language="hi-IN" voice="Polly.Aditi">
            हम Website Development और Mobile App Development की professional services provide करते हैं।
            हमारी services में Custom Website, E-Commerce Website, Android और iOS App Development शामिल हैं।
            हमारी team experienced developers से बनी है जो आपके business को digital बनाने में मदद करती है।
            हमसे callback लेने के लिए 1 दबाएं।
            Main menu पर वापस जाने के लिए 2 दबाएं।
        </Say>
    </Gather>
    <Redirect method="POST">{BASE_URL}/ivr</Redirect>
</Response>"""
    return twiml(xml)

@ivr_app.post("/ivr/web-app/handle")
async def web_app_handle(Digits: str = Form(default="")):
    if Digits.strip() == "1":
        return twiml(_callback_xml())
    return twiml(_redirect_main())


# ─────────────────────────────────────────────
# OPTION 2: Digital Marketing
# ─────────────────────────────────────────────
@ivr_app.post("/ivr/marketing")
async def marketing():
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather numDigits="1" action="{BASE_URL}/ivr/marketing/handle" method="POST" timeout="8">
        <Say language="hi-IN" voice="Polly.Aditi">
            हम Digital Marketing की complete services provide करते हैं।
            इसमें Search Engine Optimization यानी SEO, Google Ads, Social Media Marketing,
            Facebook Ads, और Content Marketing शामिल हैं।
            हम आपके business को online grow करने में मदद करते हैं।
            हमसे callback लेने के लिए 1 दबाएं।
            Main menu पर वापस जाने के लिए 2 दबाएं।
        </Say>
    </Gather>
    <Redirect method="POST">{BASE_URL}/ivr</Redirect>
</Response>"""
    return twiml(xml)

@ivr_app.post("/ivr/marketing/handle")
async def marketing_handle(Digits: str = Form(default="")):
    if Digits.strip() == "1":
        return twiml(_callback_xml())
    return twiml(_redirect_main())


# ─────────────────────────────────────────────
# OPTION 3: Pricing & Quotation
# ─────────────────────────────────────────────
@ivr_app.post("/ivr/pricing")
async def pricing():
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather numDigits="1" action="{BASE_URL}/ivr/pricing/handle" method="POST" timeout="8">
        <Say language="hi-IN" voice="Polly.Aditi">
            हमारी pricing आपके project की requirement के आधार पर तय होती है।
            एक basic website 10,000 रुपये से शुरू होती है।
            Mobile App Development 25,000 रुपये से शुरू होती है।
            Digital Marketing packages 5,000 रुपये प्रति माह से शुरू होते हैं।
            Detailed quotation के लिए हमारी team आपसे personally बात करेगी।
            Free quotation के लिए callback लेने हेतु 1 दबाएं।
            Main menu पर वापस जाने के लिए 2 दबाएं।
        </Say>
    </Gather>
    <Redirect method="POST">{BASE_URL}/ivr</Redirect>
</Response>"""
    return twiml(xml)

@ivr_app.post("/ivr/pricing/handle")
async def pricing_handle(Digits: str = Form(default="")):
    if Digits.strip() == "1":
        return twiml(_callback_xml())
    return twiml(_redirect_main())


# ─────────────────────────────────────────────
# OPTION 4: Schedule a Meeting
# ─────────────────────────────────────────────
@ivr_app.post("/ivr/meeting")
async def meeting():
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather numDigits="1" action="{BASE_URL}/ivr/meeting/handle" method="POST" timeout="8">
        <Say language="hi-IN" voice="Polly.Aditi">
            हम आपके साथ एक meeting schedule करना चाहते हैं।
            हमारे office का समय सोमवार से शनिवार, सुबह 10 बजे से शाम 7 बजे तक है।
            Meeting request के लिए हमारी team आपको call back करेगी और आपके लिए सुविधाजनक समय fix करेगी।
            Meeting request के लिए 1 दबाएं।
            Main menu पर वापस जाने के लिए 2 दबाएं।
        </Say>
    </Gather>
    <Redirect method="POST">{BASE_URL}/ivr</Redirect>
</Response>"""
    return twiml(xml)

@ivr_app.post("/ivr/meeting/handle")
async def meeting_handle(Digits: str = Form(default="")):
    if Digits.strip() == "1":
        return twiml(_callback_xml())
    return twiml(_redirect_main())


# ─────────────────────────────────────────────
# OPTION 0: Transfer to Human
# ─────────────────────────────────────────────
@ivr_app.post("/ivr/human")
async def human_transfer():
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="hi-IN" voice="Polly.Aditi">
        आपको हमारी team से connect किया जा रहा है। कृपया थोड़ा hold करें।
    </Say>
    <Dial timeout="30" callerId="{os.getenv('TWILIO_PHONE_NUMBER', '')}">
        {HUMAN_NUMBER}
    </Dial>
    <Say language="hi-IN" voice="Polly.Aditi">
        माफ़ कीजिये, हमारी team अभी available नहीं है। कृपया थोड़ी देर बाद call करें। धन्यवाद!
    </Say>
</Response>"""
    return twiml(xml)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _callback_xml() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="hi-IN" voice="Polly.Aditi">
        धन्यवाद! हमने आपकी callback request note कर ली है।
        हमारी team जल्द ही आपसे संपर्क करेगी।
        Binjwa IT Solutions को call करने के लिए बहुत बहुत धन्यवाद। नमस्कार!
    </Say>
    <Hangup/>
</Response>"""

def _redirect_main() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Redirect method="POST">{BASE_URL}/ivr</Redirect>
</Response>"""
