"""
test_agent_outbound_call.py
============================
Test the AI Agent calling customers with emotional voices.

The agent initiates outbound calls and converses with customers
using AI responses and emotional voice tones.

IMPORTANT: Make sure your server is running first!
  cd Vobiz_Working_Project
  python main_dynamic_vobiz.py

Then run this test:
  python test_agent_outbound_call.py --phone 918319688692 --name "Customer Name" --emotion happy

Examples:
  # Happy greeting with English
  python test_agent_outbound_call.py --phone 918319688692 --name "Anuj" --emotion happy

  # Professional tone with Hindi
  python test_agent_outbound_call.py --phone 919876543210 --name "राज" --emotion professional

  # Excited tone with English
  python test_agent_outbound_call.py --phone 919999999999 --name "Sarah" --emotion excited
"""

import requests
import os
import sys
import argparse
from dotenv import load_dotenv

load_dotenv()

# Configuration
BASE_URL = os.getenv("IVR_BASE_URL", "http://127.0.0.1:8000")
AUTH_ID = os.getenv("IVR_VOBIZ_AUTH_ID")
AUTH_TOKEN = os.getenv("IVR_VOBIZ_AUTH_TOKEN")
VOBIZ_PHONE = os.getenv("IVR_VOBIZ_PHONE_NUMBER")

VOBIZ_API_URL = f"https://api.vobiz.ai/api/v1/Account/{AUTH_ID}/Call/"

# Available agent emotions
AVAILABLE_EMOTIONS = ["happy", "professional", "conversational", "excited", "warm"]

def format_phone(phone: str) -> str:
    """Format phone number to +91xxxxx format"""
    phone = phone.strip()
    if len(phone) == 10 and phone.isdigit():
        return f"+91{phone}"
    elif len(phone) == 12 and phone.startswith("91"):
        return f"+{phone}"
    return phone

def trigger_agent_call(phone: str, name: str = "Customer", emotion: str = "happy", lang: str = "en"):
    """
    Trigger an outbound call where the AI Agent talks to the customer.
    
    The agent will:
    1. Greet the customer
    2. Listen to their response
    3. Generate an AI response based on their input
    4. Continue the conversation
    5. Optionally help with booking meetings
    
    Args:
        phone: Customer phone number (10 or 12 digits)
        name: Customer name
        emotion: Agent emotion (happy, professional, excited, warm, conversational)
        lang: Language (en, hi, mr, gu, pa)
    """
    
    phone = format_phone(phone)
    
    if emotion not in AVAILABLE_EMOTIONS:
        print(f"❌ Invalid emotion '{emotion}'. Available: {', '.join(AVAILABLE_EMOTIONS)}")
        return
    
    # Prepare the payload for Vobiz
    payload = {
        "from": VOBIZ_PHONE,
        "to": phone,
        "answer_url": f"{BASE_URL}/agent/outbound_call?name={name}&emotion={emotion}&lang={lang}",
        "answer_method": "GET",
        "hangup_url": f"{BASE_URL}/agent/call_ended?name={name}",
        "hangup_method": "POST",
    }
    
    print(f"\n{'='*70}")
    print(f"🤖 AI AGENT OUTBOUND CALL")
    print(f"{'='*70}")
    print(f"📞 Calling: {phone}")
    print(f"👤 Customer: {name}")
    print(f"🎭 Agent Emotion: {emotion.upper()}")
    print(f"🗣️  Language: {lang.upper()}")
    print(f"{'='*70}")
    print(f"\n⏳ The agent will now call {name}...")
    print(f"💬 Agent will greet, listen, and respond with {emotion} emotion")
    print(f"📅 Customer can ask to book a meeting by saying 'schedule' or 'appointment'")
    print(f"👋 Customer can end by saying 'bye' or 'goodbye'\n")
    
    try:
        response = requests.post(
            VOBIZ_API_URL,
            json=payload,
            headers={
                "X-Auth-ID": AUTH_ID,
                "X-Auth-Token": AUTH_TOKEN,
                "Content-Type": "application/json"
            },
            timeout=10
        )
        
        if response.status_code in [200, 201, 202]:
            data = response.json()
            call_uuid = data.get("call_uuid", data.get("CallUUID", "unknown"))
            print(f"✅ Call initiated successfully!")
            print(f"📊 Call UUID: {call_uuid}")
            print(f"{'='*70}\n")
            
            # Show how to monitor the call
            print(f"💡 To monitor this call session:")
            print(f"   curl {BASE_URL}/agent/session/{call_uuid}\n")
            
            return call_uuid
        else:
            error_msg = response.text
            try:
                error_data = response.json()
                error_msg = error_data.get("error", error_msg)
            except:
                pass
            print(f"❌ Failed to initiate call")
            print(f"📊 Status Code: {response.status_code}")
            print(f"❗ Error: {error_msg}\n")
            return None
            
    except Exception as e:
        print(f"❌ Exception: {e}\n")
        return None

def list_active_sessions():
    """Show all active agent call sessions"""
    try:
        response = requests.get(f"{BASE_URL}/agent/sessions")
        if response.status_code == 200:
            data = response.json()
            print(f"\n🤖 Active Agent Call Sessions: {data['active_sessions']}")
            if data['active_sessions'] > 0:
                for session in data['sessions']:
                    print(f"\n  📞 {session['customer_name']}")
                    print(f"     Emotion: {session['emotion']}")
                    print(f"     Language: {session['language']}")
                    print(f"     Duration: {session['duration_seconds']:.1f}s")
                    print(f"     Messages: {session['messages']}")
            print()
    except Exception as e:
        print(f"❌ Failed to fetch sessions: {e}\n")

def main():
    parser = argparse.ArgumentParser(
        description="Trigger an AI Agent outbound call with emotional voice",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Happy greeting with English
  python test_agent_outbound_call.py --phone 918319688692 --name "Anuj" --emotion happy

  # Professional tone with Hindi
  python test_agent_outbound_call.py --phone 919876543210 --name "राज" --emotion professional

  # Excited tone (English male voice)
  python test_agent_outbound_call.py --phone 919999999999 --name "Sarah" --emotion excited

  # List all active calls
  python test_agent_outbound_call.py --list
        """
    )
    parser.add_argument("--phone", help="Customer phone number (10 or 12 digits)")
    parser.add_argument("--name", default="Customer", help="Customer name (default: Customer)")
    parser.add_argument("--emotion", default="happy", choices=AVAILABLE_EMOTIONS,
                       help="Agent emotion (default: happy)")
    parser.add_argument("--lang", default="en", choices=["en", "hi", "mr", "gu", "pa"],
                       help="Language (default: en)")
    parser.add_argument("--list", action="store_true", help="List all active agent call sessions")
    
    args = parser.parse_args()
    
    if args.list:
        list_active_sessions()
    elif args.phone:
        trigger_agent_call(
            phone=args.phone,
            name=args.name,
            emotion=args.emotion,
            lang=args.lang
        )
    else:
        parser.print_help()

if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("\n" + "="*70)
        print("🤖 AI AGENT OUTBOUND CALLING SYSTEM")
        print("="*70)
        print("\nTrigger AI Agent outbound calls with emotional voices!\n")
        print("Usage:")
        print("  python test_agent_outbound_call.py --phone 918319688692 --name 'John' --emotion happy")
        print("\nAvailable emotions:")
        for emotion in AVAILABLE_EMOTIONS:
            print(f"  - {emotion}")
        print("\nLanguages supported:")
        print("  - en (English)")
        print("  - hi (Hindi)")
        print("  - mr (Marathi)")
        print("  - gu (Gujarati)")
        print("  - pa (Punjabi)")
        print("\nMonitor active sessions:")
        print("  python test_agent_outbound_call.py --list")
        print()
    else:
        main()
