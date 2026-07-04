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

import requests

def send_aisensy_whatsapp_confirmation(customer_number: str, name: str, meeting_time: str):
    """
    Send a WhatsApp confirmation message using AiSensy's Campaign API.
    customer_number should be without the '+' sign (e.g., '918319688692').
    """
    api_key = os.getenv("AISENSY_API_KEY")
    campaign_name = os.getenv("AISENSY_CAMPAIGN_NAME")
    
    if not api_key or not campaign_name:
        print("⚠️ AISENSY_API_KEY or AISENSY_CAMPAIGN_NAME not found in .env. Skipping AiSensy message.")
        return False
        
    # Remove '+' if it exists in the customer number
    clean_number = customer_number.replace("+", "")
        
    url = "https://backend.aisensy.com/campaign/t1/api/v2"
    
    # payload matches the template variables: {{1}} for Name, {{2}} for Time
    payload = {
        "apiKey": api_key,
        "campaignName": campaign_name,
        "destination": clean_number,
        "userName": name,
        "templateParams": [
            name,          # {{1}} in template
            meeting_time   # {{2}} in template
        ]
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            print(f"✅ AiSensy WhatsApp message sent! Response: {response.json()}")
            return True
        else:
            print(f"❌ Failed to send AiSensy message. Status: {response.status_code}, Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ AiSensy request failed: {e}")
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

