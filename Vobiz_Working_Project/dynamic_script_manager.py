"""
dynamic_script_manager.py — Dynamic Node Flow Manager (MongoDB)
--------------------------------------------------------------
Allows React Flow drag-and-drop IVR node trees to be saved and retrieved
dynamically per tenant. This is a brand new file to support dynamic workflows
without modifying any old files.
"""

import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pymongo import MongoClient, errors as mongo_errors
from pymongo.collection import Collection

load_dotenv(override=True)

MONGO_URI     = os.getenv("IVR_MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("IVR_MONGO_DB_NAME", "Binjwa_IT_Solutions")

_client: MongoClient = None
_collection: Collection = None

def get_collection() -> Collection:
    """Returns the IVR_Flows MongoDB collection."""
    global _client, _collection
    if _collection is None:
        try:
            _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            db = _client[MONGO_DB_NAME]
            _collection = db["IVR_Flows"]
            _collection.create_index("webhookId", unique=True)
            print(f"✅ [DynamicScriptManager] Connected to MongoDB: {MONGO_DB_NAME}.IVR_Flows")
        except mongo_errors.ServerSelectionTimeoutError:
            print("❌ [DynamicScriptManager] MongoDB connection failed.")
            _collection = None
    return _collection

DEFAULT_FLOW = {
    "language": "hi",
    "start_node": "node_greeting",
    "nodes": {
        "node_greeting": {
            "type": "menu",
            "text": (
                "Hello {name}, first of all congratulations for your new business! "
                "I am calling from बिंजवा IT Solutions. We provide complete solutions "
                "for your business. Meeting schedule करने के लिए 1 दबाएँ। "
                "हमारी sales team से बात करने के लिए 2 दबाएँ।"
            ),
            "branches": {
                "1": "node_ask_time",
                "2": "node_forward_sales"
            },
            "invalid_text": "Invalid option. कृपया 1 या 2 दबाएँ।"
        },
        "node_ask_time": {
            "type": "action_record",
            "text": "बहुत बढ़िया {name} जी। कृपया बताएँ कि आप किस दिन और कितने बजे मीटिंग करना चाहते हैं?",
            "next_node": "node_booking_confirm"
        },
        "node_booking_confirm": {
            "type": "action_book_meeting",
            "text": "बहुत अच्छा! {name} जी, हमने आपकी request ले ली है। हमारी team जल्द ही calendar check करके आपको SMS भेज देगी। बिंजवा IT Solutions को समय देने के लिए धन्यवाद!",
            "end_call": True
        },
        "node_forward_sales": {
            "type": "action_forward",
            "text": "ठीक है! हमारी sales team जल्द ही आपसे संपर्क करेगी। बिंजवा IT Solutions को समय देने के लिए धन्यवाद। आपका दिन शुभ हो।",
            "forward_number": "+919302565968",
            "end_call": True
        }
    }
}

DEFAULT_FLOW_EN = {
    "language": "en",
    "start_node": "node_greeting",
    "nodes": {
        "node_greeting": {
            "type": "menu",
            "text": (
                "Hello {name}, first of all congratulations for your new business! "
                "I am calling from Binjwa IT Solutions. We provide complete solutions "
                "for your business. To schedule a meeting, press 1. "
                "To talk to our sales team, press 2."
            ),
            "branches": {
                "1": "node_ask_time",
                "2": "node_forward_sales"
            },
            "invalid_text": "Invalid option. Please press 1 or 2."
        },
        "node_ask_time": {
            "type": "action_record",
            "text": "Great {name}. Please tell me what day and time you would like to schedule the meeting?",
            "next_node": "node_booking_confirm"
        },
        "node_booking_confirm": {
            "type": "action_book_meeting",
            "text": "Excellent {name}, we have received your request. Our team will check the calendar and send you an SMS shortly. Thank you for giving your time to Binjwa IT Solutions!",
            "end_call": True
        },
        "node_forward_sales": {
            "type": "action_forward",
            "text": "Alright! Our sales team will contact you shortly. Thank you for giving your time to Binjwa IT Solutions. Have a good day.",
            "forward_number": "+918827614849",
            "end_call": True
        }
    }
}

DEFAULT_FLOW_MR = {
    "language": "mr",
    "start_node": "node_greeting",
    "nodes": {
        "node_greeting": {
            "type": "menu",
            "text": "नमस्कार {name}, बिंजवा IT Solutions मध्ये आपले स्वागत आहे. मीटिंग शेड्यूल करण्यासाठी 1 दाबा. आमच्या सेल्स टीमशी बोलण्यासाठी 2 दाबा.",
            "branches": {
                "1": "node_ask_time",
                "2": "node_forward_sales"
            },
            "invalid_text": "अवैध पर्याय. कृपया 1 किंवा 2 दाबा."
        },
        "node_ask_time": {
            "type": "action_record",
            "text": "उत्तम {name}. कृपया सांगा तुम्ही कोणत्या दिवशी आणि किती वाजता मीटिंग शेड्यूल करू इच्छिता?",
            "next_node": "node_booking_confirm"
        },
        "node_booking_confirm": {
            "type": "action_book_meeting",
            "text": "उत्तम {name}, आम्हाला तुमची विनंती मिळाली आहे. आमची टीम लवकरच कॅलेंडर तपासेल आणि तुम्हाला SMS पाठवेल. धन्यवाद!",
            "end_call": True
        },
        "node_forward_sales": {
            "type": "action_forward",
            "text": "ठीक आहे! आमची सेल्स टीम लवकरच तुमच्याशी संपर्क साधेल. धन्यवाद. तुमचा दिवस शुभ असो.",
            "forward_number": "+919302565968",
            "end_call": True
        }
    }
}

def get_flow(webhookId: str, lang: str = None) -> dict:
    """Fetch the JSON flow for a specific webhookId."""
    # We will try to fetch from DB first, if not found return DEFAULT_FLOW
    # If the user sets 'language=en' in query (handled downstream), they might override.
    # But for script manager, it just returns what's in DB.
    
    flow = None
    if webhookId:
        try:
            col = get_collection()
            if col is not None:
                doc = col.find_one({"webhookId": webhookId}, {"_id": 0})
                if doc and "flow_json" in doc:
                    flow = doc["flow_json"]
        except Exception as e:
            print(f"⚠️ [DynamicScriptManager] MongoDB read error for '{webhookId}': {e}")

    if not flow:
        if lang and lang.lower() == "en":
            flow = DEFAULT_FLOW_EN
        elif lang and lang.lower() == "mr":
            flow = DEFAULT_FLOW_MR
        else:
            flow = DEFAULT_FLOW

    # If the flow in DB explicitly says language="en" but they haven't modified nodes, 
    # we could swap it, but usually the DB flow is what they saved.
    # If the flow explicitly specifies 'en', we ensure it's treated as english.
    
    # If query param lang="en" is passed, override the flow language temporarily
    if lang and lang.lower() == "en":
        # Make a copy so we don't mutate the cached/db object
        import copy
        flow = copy.deepcopy(flow)
        flow["language"] = "en"

    return flow

def save_flow(webhookId: str, flow_json: dict) -> bool:
    """Save a JSON flow for a specific webhookId."""
    try:
        col = get_collection()
        if col is None:
            return False
        col.update_one(
            {"webhookId": webhookId},
            {"$set": {
                "webhookId": webhookId,
                "flow_json": flow_json,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
        return True
    except Exception as e:
        print(f"❌ [DynamicScriptManager] Failed to save flow for '{webhookId}': {e}")
        return False

# ─────────────────────────────────────────────
# REST API ROUTER
# ─────────────────────────────────────────────
router = APIRouter(prefix="/scripts", tags=["Dynamic Script Manager"])

@router.get("/flow/{webhookId}")
async def api_get_flow(webhookId: str):
    """Retrieve the node workflow tree for a tenant."""
    flow = get_flow(webhookId)
    return JSONResponse({"webhookId": webhookId, "flow": flow})

@router.post("/flow/{webhookId}")
async def api_save_flow(webhookId: str, request: Request):
    """Save the entire node workflow JSON tree."""
    try:
        flow_json = await request.json()
    except:
        return JSONResponse({"error": "Invalid JSON payload."}, status_code=400)

    if "start_node" not in flow_json or "nodes" not in flow_json:
        return JSONResponse({"error": "JSON must contain 'start_node' and 'nodes' objects."}, status_code=400)

    if save_flow(webhookId, flow_json):
        print(f"✅ [DynamicScriptManager] Saved dynamic flow for '{webhookId}'.")
        return JSONResponse({"status": "success", "message": f"Flow saved for {webhookId}"})
    return JSONResponse({"error": "Failed to save flow to database."}, status_code=500)
