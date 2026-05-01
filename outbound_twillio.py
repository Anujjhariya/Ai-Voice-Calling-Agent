"""
outbound_twilio.py
------------------
Makes an outbound call using Twilio.
Your server calls the customer → customer picks up → AI agent speaks.
"""

import os
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

def make_outbound_call(customer_number: str):
    """
    customer_number: Indian mobile number with country code
    Example: +919876543210
    """
    client = Client(
        os.getenv("TWILIO_ACCOUNT_SID"),
        os.getenv("TWILIO_AUTH_TOKEN")
    )

    BASE_URL = os.getenv("BASE_URL")

    call = client.calls.create(
        to=customer_number,
        from_=os.getenv("TWILIO_PHONE_NUMBER"),
        url=f"{BASE_URL}/twiml",   # Twilio hits this when customer picks up
        record=True                # optional — records the call
    )

    print(f"✅ Call initiated!")
    print(f"   To:     {customer_number}")
    print(f"   SID:    {call.sid}")
    print(f"   Status: {call.status}")
    return call.sid


if __name__ == "__main__":
    # Put the number you want to call here
    # Must be verified in Twilio trial account
    # make_outbound_call("+918319688692")  # ← your mobile number here
    make_outbound_call("+918319688692")  # ← your mobile number here