import os
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

def send_whatsapp_confirmation(customer_number: str, name: str, meeting_time: str):
    """
    Send a WhatsApp confirmation message using Twilio's WhatsApp API.
    customer_number must be in E.164 format (e.g. +918319688692).
    Twilio handles sending it as 'whatsapp:+91...'
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    
    # Check if TWILIO_WHATSAPP_NUMBER is in .env, if not, fallback to a dummy sandbox number
    # You MUST set TWILIO_WHATSAPP_NUMBER in your .env (e.g. whatsapp:+14155238886)
    from_whatsapp = os.getenv("TWILIO_WHATSAPP_NUMBER")
    if not from_whatsapp:
        print("⚠️ TWILIO_WHATSAPP_NUMBER not found in .env. Skipping WhatsApp message.")
        return False
        
    client = Client(account_sid, auth_token)

    message_body = (
        f"नमस्कार {name} जी! 👋\n\n"
        f"Binjwa IT Solutions से बात करने के लिए धन्यवाद।\n\n"
        f"📅 आपकी मीटिंग फिक्स हो गई है:\n"
        f"⏰ समय: {meeting_time}\n\n"
        f"हमारी टीम आपसे जल्द ही संपर्क करेगी। 😊"
    )

    try:
        message = client.messages.create(
            from_=from_whatsapp,
            body=message_body,
            to=f"whatsapp:{customer_number}"
        )
        print(f"✅ WhatsApp message sent! SID: {message.sid}")
        return True
    except Exception as e:
        print(f"❌ Failed to send WhatsApp message: {e}")
        return False

def get_customer_number_from_call(call_sid: str) -> str:
    """Fetch the customer's phone number from the Twilio Call SID."""
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    client = Client(account_sid, auth_token)
    
    try:
        call = client.calls(call_sid).fetch()
        return call.to  # This is the customer's number
    except Exception as e:
        print(f"❌ Could not fetch call details for WhatsApp: {e}")
        return ""
