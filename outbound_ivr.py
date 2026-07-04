"""
outbound_ivr.py
---------------
Makes an outbound call that plays the IVR menu (NOT the AI agent).
Customer picks up → IVR greeting plays → they press keys to navigate.
"""

import os
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

def make_ivr_call(customer_number: str):
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
        url=f"{BASE_URL}/ivr/welcome",   # ← IVR (NOT AI agent)
        record=True
    )

    print(f"✅ IVR Call initiated!")
    print(f"   To:     {customer_number}")
    print(f"   SID:    {call.sid}")
    print(f"   Status: {call.status}")
    return call.sid


if __name__ == "__main__":
    # Put the number you want to call here
    # Must be verified in Twilio trial account
    make_ivr_call("+919302565968")   # ← your mobile number here
