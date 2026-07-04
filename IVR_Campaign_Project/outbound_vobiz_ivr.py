import os
import requests
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

AUTH_ID    = os.getenv("VOBIZ_AUTH_ID")
AUTH_TOKEN = os.getenv("VOBIZ_AUTH_TOKEN")
BASE_URL   = os.getenv("BASE_URL")  # your ngrok/server URL
VOBIZ_PHONE = os.getenv("VOBIZ_PHONE_NUMBER")

def make_vobiz_ivr_call(customer_number: str, customer_name: str = "Customer"):
    """
    Triggers an outbound call via Vobiz that starts with the IVR menu.
    """
    if not BASE_URL:
        print("Error: BASE_URL not found in .env")
        return

    url = f"https://api.vobiz.ai/api/v1/Account/{AUTH_ID}/Call/"

    encoded_name = urllib.parse.quote(customer_name)
    payload = {
        "from": VOBIZ_PHONE,
        "to":   customer_number,
        "answer_url": f"{BASE_URL}/ivr/welcome?name={encoded_name}",   # ← IVR entry point
        "answer_method": "GET",
        "hangup_url": f"{BASE_URL}/ivr/hangup",
        "hangup_method": "POST",
    }

    print(f"Calling {customer_number} via Vobiz (IVR mode)...")
    
    response = requests.post(
        url,
        json=payload,
        headers={
            "X-Auth-ID":    AUTH_ID,
            "X-Auth-Token": AUTH_TOKEN,
            "Content-Type": "application/json"
        }
    )

    if response.status_code in [200, 201, 202]:
        data = response.json()
        uuid = data.get('call_uuid', '')
        print(f"Call triggered successfully!")
        print(f"   Call UUID: {uuid}")
        return uuid
    else:
        print(f"Failed to trigger call: {response.status_code}")
        print(f"   Response: {response.text}")
        return None

if __name__ == "__main__":
    # Test number
    # target_number = "+919302565968" 
    target_number = "+918319688692" 
    make_vobiz_ivr_call(target_number, "Rahul")
