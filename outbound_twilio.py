import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

# The ngrok URL of your FastAPI server
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.0:8000")
TRIGGER_URL = f"{BASE_URL}/api/trigger_twilio_call"

# Customer Details
payload = {
    "name": "Vivek",
    "phone": "+918319688692"
}

headers = {
    "Content-Type": "application/json"
}

print(f"🚀 Triggering Twilio AI Call to {payload['phone']}...")
response = requests.post(TRIGGER_URL, json=payload, headers=headers)

if response.status_code == 200:
    print(f"✅ Call triggered! Response: {response.json()}")
else:
    print(f"❌ Failed to trigger call: {response.status_code}")
    print(response.text)
