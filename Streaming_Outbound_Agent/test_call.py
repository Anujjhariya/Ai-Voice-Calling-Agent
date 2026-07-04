import argparse
import requests

# def test_outbound_call(phone: str, name: str, lang: str):
#     url = f"http://127.0.0.1:8000/api/make_call"
#     params = {
#         "phone": phone,
#         "name": name,
#         "lang": lang
#     }
    
#     print(f"📞 Initiating STREAMING outbound call to {phone}...")
#     try:
#         response = requests.post(url, params=params)
#         print("Response Status:", response.status_code)
#         print("Response Body:", response.json())
#         if response.status_code == 200:
#             print(f"✅ Call initiated successfully. Check terminal for WebSocket logs.")
#         else:
#             print(f"❌ Failed to initiate call.")
#     except Exception as e:
#         print(f"❌ Error connecting to FastAPI server: {e}")
#         print("Make sure 'python main.py' is running on port 8000.")


def test_outbound_call(phone: str, name: str, lang: str):
    url = "http://127.0.0.1:8000/api/trigger_ai_call"   # ← naya endpoint
    payload = {                                          # ← JSON body, params nahi
        "phone_number": phone,
        "customer_name": name,
        "lang": lang
    }

    print(f"📞 Initiating STREAMING outbound call to {phone}...")
    try:
        response = requests.post(url, json=payload)      # ← json= use karo
        print("Response Status:", response.status_code)
        print("Response Body:", response.json())
        if response.status_code == 200:
            print("✅ Call initiated successfully.")
        else:
            print("❌ Failed to initiate call.")
    except Exception as e:
        print(f"❌ Error connecting to FastAPI server: {e}")



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Streaming Outbound Agent")
    parser.add_argument("--phone", required=True, help="Phone number to call (with country code, e.g., 919876543210)")
    parser.add_argument("--name", default="Anuj", help="Name of the customer")
    parser.add_argument("--lang", default="hi", choices=["en", "hi", "mr", "gu", "pa"], help="Language code")
    
    args = parser.parse_args()
    test_outbound_call(args.phone, args.name, args.lang)
