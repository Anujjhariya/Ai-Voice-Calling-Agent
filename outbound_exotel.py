import os
import requests
from dotenv import load_dotenv

load_dotenv()

def trigger_outbound_call(customer_number):
    """
    Trigger an outbound call via Exotel Connect API.
    Docs: https://support.exotel.com/support/solutions/articles/48259
    
    Flow: Calls 'From' first → once picked up → connects to 'To'
    For voicebot: From = ExoPhone, To = Customer
    """
    sid    = os.getenv("EXOTEL_SID")
    key    = os.getenv("EXOTEL_API_KEY")
    token  = os.getenv("EXOTEL_API_TOKEN")
    caller = os.getenv("EXOTEL_PHONE_NUMBER")
    base   = os.getenv("BASE_URL", "")

    # Exotel docs: credentials go in the URL
    # Subdomain: api.exotel.com (Singapore) or api.in.exotel.com (Mumbai)
    url = f"https://{key}:{token}@api.exotel.com/v1/Accounts/{sid}/Calls/connect.json"
    
    # Exotel docs: mobile numbers must be prefixed with 0
    # e.g., 09302565968 (NOT 9302565968)
    clean = customer_number.replace("+91", "").replace(" ", "")
    if not clean.startswith("0"):
        clean = "0" + clean
    
    payload = {
        "From": caller,           # ExoPhone — called first
        "To": clean,              # Customer — connected after
        "CallerId": caller,       # Must be your ExoPhone
        "CallType": "trans",
    }

    print(f"📞 Calling {clean} via Exotel...")
    print(f"   From (ExoPhone): {caller}")
    print(f"   Account: {sid}")

    response = requests.post(url, data=payload)
    
    if response.status_code == 200:
        print(f"✅ Call triggered successfully!")
        print(f"   {response.text[:300]}")
    else:
        print(f"❌ Failed: {response.status_code}")
        print(f"   {response.text[:500]}")

if __name__ == "__main__":
    trigger_outbound_call("9302565968")
