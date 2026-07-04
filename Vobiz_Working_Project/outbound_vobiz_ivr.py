import os
import requests
import urllib.parse
from dotenv import load_dotenv

load_dotenv(override=True)

AUTH_ID    = os.getenv("IVR_VOBIZ_AUTH_ID")
AUTH_TOKEN = os.getenv("IVR_VOBIZ_AUTH_TOKEN")
BASE_URL   = os.getenv("IVR_BASE_URL")  # your ngrok/server URL
VOBIZ_PHONE = os.getenv("IVR_VOBIZ_PHONE_NUMBER")

def make_vobiz_ivr_call(customer_number: str, customer_name: str = "Customer", voice: str = "Polly.Aditi", webhookId: str = ""):
    """
    Triggers an outbound call via our internal API that starts with the IVR menu.
    """
    if not BASE_URL:
        print("Error: BASE_URL not found in .env")
        return

    # Trigger via localhost directly (avoids ngrok round-trip which causes 503)
    trigger_url = "http://localhost:8000/ivr/trigger_single_call"
    
    payload = {
        "phone": customer_number,
        "name": customer_name,
        "voice": voice,
        "webhookId": webhookId
    }

    print(f"Calling {customer_number} via API (IVR mode) with voice '{voice}'...")
    
    response = requests.post(
        trigger_url,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=15
    )

    if response.status_code in [200, 201, 202]:
        data = response.json()
        print(f"Call triggered successfully!")
        print(f"Response: {data}")
        return data
    else:
        print(f"Failed to trigger call: {response.status_code}")
        print(f"Response: {response.text}")
        return None

if __name__ == "__main__":
    # Test number
    # target_number = "+918319688692" 
    target_number = "+919644260383"
       # target_number = "+919340155262" 
    # target_number = "+919644260383" 
    
    # Use Polly.Aditi to guarantee Vobiz/Plivo compatibility
    make_vobiz_ivr_call(target_number, "Tarun", voice="Polly.Aditi")
