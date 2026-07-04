import os
import requests
from dotenv import load_dotenv

load_dotenv()

AUTH_ID    = os.getenv("VOBIZ_AUTH_ID")
AUTH_TOKEN = os.getenv("VOBIZ_AUTH_TOKEN")
BASE_URL   = os.getenv("BASE_URL")  # your ngrok/server URL

def make_outbound_call(customer_number: str):
    """Make outbound call via Vobiz — triggers your AI agent"""
    url = f"https://api.vobiz.ai/api/v1/Account/{AUTH_ID}/Call/"

    payload = {
        "from": os.getenv("VOBIZ_PHONE_NUMBER"),
        "to":   customer_number,
        "answer_url": f"{BASE_URL}/incoming",   # Vobiz hits this on pickup
        "answer_method": "POST",
        "hangup_url": f"{BASE_URL}/hangup",
        "hangup_method": "POST",
    }

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
        print(f"✅ Call triggered! UUID: {data.get('call_uuid', '')}")
        return data.get("call_uuid", "")
    else:
        print(f"❌ Failed: {response.status_code} — {response.text}")
        return ""


if __name__ == "__main__":
    make_outbound_call("+918319688692")