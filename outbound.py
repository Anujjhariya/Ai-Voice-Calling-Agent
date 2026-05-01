import os
import requests
from dotenv import load_dotenv

load_dotenv()

def trigger_outbound_call(customer_number):
    # Exotel API URL for initiating a call
    # The 'Url' parameter is where Exotel will go for instructions once the user picks up
    url = f"https://api.exotel.com/v1/Accounts/{os.getenv('EXOTEL_SID')}/Calls/connect.json"
    
    auth = (os.getenv("EXOTEL_API_KEY"), os.getenv("EXOTEL_API_TOKEN"))
    
    payload = {
        "From": os.getenv("EXOTEL_PHONE_NUMBER"),
        "To": customer_number,
        "CallerId": os.getenv("EXOTEL_PHONE_NUMBER"),
        # IMPORTANT: Use wss:// for the Voicebot applet logic
        "Url": f"wss://{os.getenv('BASE_URL').replace('https://', '')}/ws", 
        "CallType": "trans",
        "Record": "true"
    }

    response = requests.post(url, auth=auth, data=payload)
    
    if response.status_code == 200:
        print(f"✅ Call triggered successfully to {customer_number}")
    else:
        print(f"❌ Failed to trigger call: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    # Use your verified mobile number with the country code prefix (0 or +91)
    trigger_outbound_call("8319688692")