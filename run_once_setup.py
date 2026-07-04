# run_once_setup.py — run this ONCE to register your app with Vobiz
import os, requests
from dotenv import load_dotenv
load_dotenv()

AUTH_ID    = os.getenv("VOBIZ_AUTH_ID")
AUTH_TOKEN = os.getenv("VOBIZ_AUTH_TOKEN")
BASE_URL   = os.getenv("BASE_URL")  # your current ngrok URL

print(f"AUTH_ID:  {AUTH_ID}")
print(f"BASE_URL: {BASE_URL}")

# ── Step 1: Create the Application ────────────────────────
resp = requests.post(
    f"https://api.vobiz.ai/api/v1/Account/{AUTH_ID}/Application/",
    headers={
        "X-Auth-ID":    AUTH_ID,
        "X-Auth-Token": AUTH_TOKEN,
        "Content-Type": "application/json"
    },
    json={
        "app_name":      "Binjwa AI Voice Agent",
        "answer_url":    f"{BASE_URL}/incoming",
        "answer_method": "POST",
        "hangup_url":    f"{BASE_URL}/hangup",
        "hangup_method": "POST",
    }
)

data = resp.json()
print("\nApp created:", data)
app_id = data.get("app_id", "")

if not app_id:
    print("❌ Failed to get app_id. Check AUTH_ID and AUTH_TOKEN in .env")
    exit()

print(f"✅ app_id: {app_id}")

# ── Step 2: Link phone number to this Application ─────────
phone_number = os.getenv("VOBIZ_PHONE_NUMBER")  # e.g. 911171366938
print(f"\nLinking number: {phone_number}")

link_resp = requests.post(   # ← lowercase .post (fixed bug)
    f"https://api.vobiz.ai/api/v1/Account/{AUTH_ID}/Application/{app_id}/",
    headers={
        "X-Auth-ID":    AUTH_ID,
        "X-Auth-Token": AUTH_TOKEN,
        "Content-Type": "application/json"
    },
    json={"numbers": [phone_number]}
)

print("Number linked:", link_resp.json())
print("\n✅ Setup complete! You only need to run this once.")
print(f"   Save your app_id somewhere: {app_id}")