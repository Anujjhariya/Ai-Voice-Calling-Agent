import os
import requests
import asyncio

def push_to_crm(payload: dict):
    """Push event data to the CRM Webhook in the background."""
    webhook_url = os.getenv("IVR_CRM_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return
        
    def do_push():
        try:
            res = requests.post(webhook_url, json=payload, 
                                headers={"Content-Type": "application/json"},
                                timeout=3)
            print(f"🌐 [CRM Webhook] {payload.get('event_type')}: HTTP {res.status_code}")
        except Exception as e:
            print(f"⚠️ [CRM Webhook] Skipped ({e.__class__.__name__})")
            
    import threading
    threading.Thread(target=do_push, daemon=True).start()
