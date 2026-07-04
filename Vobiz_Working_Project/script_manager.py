"""
script_manager.py — Dynamic IVR Script Manager (MongoDB)
----------------------------------------------------------
Allows IVR scripts to be managed dynamically via API.

Features:
  - Scripts stored in MongoDB (collection: ivr_scripts)
  - Full CRUD REST API (GET, POST, PUT, DELETE)
  - Template variable support: {name}, {time}, {company} etc.
  - Falls back to built-in defaults if no custom script in DB

Environment Variables Required:
  MONGO_URI      = mongodb://localhost:27017   (or MongoDB Atlas URI)
  MONGO_DB_NAME  = binjwa_ivr

API Endpoints (prefix: /scripts):
  GET    /scripts/              - List all scripts
  GET    /scripts/keys          - List all script keys
  GET    /scripts/{key}         - Get one script
  POST   /scripts/              - Create or update a script
  DELETE /scripts/{key}         - Delete (reverts to default)
  GET    /scripts/preview/{key} - Preview with sample variables

Usage in ivr.py:
  from script_manager import get_script
  text = get_script("ivr_greeting", {"name": "Tarun"})
"""

import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pymongo import MongoClient, errors as mongo_errors
from pymongo.collection import Collection

load_dotenv()

# ─────────────────────────────────────────────
# MONGODB CONNECTION
# ─────────────────────────────────────────────

MONGO_URI     = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "Binjwa_IT_Solutions")

_client: MongoClient = None
_collection: Collection = None

def get_collection() -> Collection:
    """Returns the ivr_scripts MongoDB collection (lazy init)."""
    global _client, _collection
    if _collection is None:
        try:
            _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            _client.server_info()  # Force connection check
            db = _client[MONGO_DB_NAME]
            _collection = db["IVR"]
            _collection.create_index("key", unique=True)
            print(f"✅ [ScriptManager] Connected to MongoDB: {MONGO_DB_NAME}.IVR")
        except mongo_errors.ServerSelectionTimeoutError:
            print("❌ [ScriptManager] MongoDB connection failed. Using default scripts only.")
            _collection = None
    return _collection


# ─────────────────────────────────────────────
# DEFAULT SCRIPTS
# Used as fallback when no custom script in MongoDB.
# ─────────────────────────────────────────────

DEFAULT_SCRIPTS = {
    "ivr_greeting": {
        "text": (
            "Hello {name}, first of all congratulations for your new business! "
            "I am calling from Binjwa IT Solutions. We provide complete solutions "
            "for your business from legal consultancy, compliance management, "
            "digital marketing, to website and app development. "
            "Meeting schedule करने के लिए 1 दबाएँ। "
            "हमारी sales team से बात करने के लिए 2 दबाएँ।"
        ),
        "description": "Main IVR greeting when customer picks up. Supports {name}."
    },
    "ivr_interested_response": {
        "text": "बहुत बढ़िया {name} जी। कृपया बताएँ कि आप किस दिन और कितने बजे मीटिंग करना चाहते हैं?",
        "description": "Played when user presses 1 (book meeting). Supports {name}."
    },
    "ivr_sales_response": {
        "text": "ठीक है! हमारी sales team जल्द ही आपसे संपर्क करेगी। Binjwa IT Solutions को समय देने के लिए धन्यवाद। आपका दिन शुभ हो।",
        "description": "Played when user presses 2 (talk to sales team)."
    },
    "ivr_booking_confirmed": {
        "text": "बहुत अच्छा! {name} जी, हमने आपकी {time} की request ले ली है।",
        "description": "Played after meeting time recorded. Supports {name}, {time}."
    },
    "ivr_booking_followup": {
        "text": "हमारी team जल्द ही calendar check करके आपको SMS भेज देगी। Binjwa IT Solutions को समय देने के लिए धन्यवाद!",
        "description": "Follow-up line played right after booking_confirmed."
    },
    "ivr_no_response": {
        "text": "कोई response नहीं मिली।",
        "description": "Played when customer doesn't press any key."
    },
    "ivr_invalid_option": {
        "text": "Invalid option। कृपया 1 या 2 दबाएँ।",
        "description": "Played when customer presses an invalid key."
    },
    "ivr_fallback_retry": {
        "text": (
            "माफ़ कीजिए, मुझे सुनाई नहीं दिया, क्या आप रिपीट कर सकते हैं "
            "कि आप सोमवार से शुक्रवार के बीच किस दिन और कितने बजे मीटिंग करना चाहते हैं?"
        ),
        "description": "Played when voice recording is not understood. Asks to repeat."
    },
    "ivr_fallback_giveup": {
        "text": (
            "कोई बात नहीं {name} जी। आप बाद में हमें call कर सकते हैं। "
            "Binjwa IT Solutions को समय देने के लिए बहुत धन्यवाद। आपका दिन शुभ हो।"
        ),
        "description": "Played after 2 failed retries. Supports {name}."
    },
    "ai_greeting": {
        "text": (
            "Hello! I am calling from Binjwa IT Solutions. "
            "We provide legal consultancy, digital marketing, and web development services. "
            "How can I help you today?"
        ),
        "description": "Opening greeting for the AI conversational agent."
    },
}


# ─────────────────────────────────────────────
# CORE FUNCTIONS — Use these in ivr.py / main_vobiz.py
# ─────────────────────────────────────────────

def get_script(key: str, variables: dict = None) -> str:
    """
    Get script text by key. Applies template variables.
    Falls back to DEFAULT_SCRIPTS if not in MongoDB.

    Example:
        get_script("ivr_greeting", {"name": "Tarun"})
        → "Hello Tarun, first of all..."
    """
    text = None

    # 1. Try MongoDB
    try:
        col = get_collection()
        if col is not None:
            doc = col.find_one({"key": key}, {"_id": 0})
            if doc:
                text = doc.get("script_text")
    except Exception as e:
        print(f"⚠️ [ScriptManager] MongoDB read error for '{key}': {e}")

    # 2. Fall back to default
    if not text:
        default = DEFAULT_SCRIPTS.get(key)
        if default:
            text = default["text"]
        else:
            print(f"⚠️ [ScriptManager] No script found for key: '{key}'")
            return f"[Script missing: {key}]"

    # 3. Apply template variables
    if variables:
        try:
            text = text.format(**variables)
        except KeyError as e:
            print(f"⚠️ [ScriptManager] Missing variable {e} in script '{key}'")

    return text


def set_script(key: str, text: str, description: str = "") -> bool:
    """Save or update a script in MongoDB."""
    try:
        col = get_collection()
        if col is None:
            return False
        col.update_one(
            {"key": key},
            {"$set": {
                "key": key,
                "script_text": text,
                "description": description,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
        return True
    except Exception as e:
        print(f"❌ [ScriptManager] Failed to save '{key}': {e}")
        return False


def delete_script(key: str) -> bool:
    """Delete a custom script from MongoDB (reverts to default)."""
    try:
        col = get_collection()
        if col is None:
            return False
        col.delete_one({"key": key})
        return True
    except Exception as e:
        print(f"❌ [ScriptManager] Failed to delete '{key}': {e}")
        return False


def list_scripts() -> list:
    """Return all scripts — DB custom ones merged with defaults."""
    result = {}

    # Start with defaults
    for key, val in DEFAULT_SCRIPTS.items():
        result[key] = {
            "key": key,
            "script_text": val["text"],
            "description": val["description"],
            "source": "default",
            "updated_at": None
        }

    # Overlay with custom MongoDB scripts
    try:
        col = get_collection()
        if col is not None:
            for doc in col.find({}, {"_id": 0}):
                result[doc["key"]] = {
                    "key": doc["key"],
                    "script_text": doc.get("script_text", ""),
                    "description": doc.get("description", ""),
                    "source": "custom",
                    "updated_at": doc.get("updated_at")
                }
    except Exception as e:
        print(f"⚠️ [ScriptManager] DB list error: {e}")

    return list(result.values())


# ─────────────────────────────────────────────
# REST API ROUTER
# Mount this in main_vobiz.py:
#   from script_manager import router as scripts_router
#   app.include_router(scripts_router)
# ─────────────────────────────────────────────

router = APIRouter(prefix="/scripts", tags=["Script Manager"])


@router.get("/")
async def api_list_scripts():
    """List all scripts (defaults + custom)."""
    return JSONResponse({"scripts": list_scripts()})


@router.get("/keys")
async def api_list_keys():
    """List all available script keys."""
    all_keys = set(DEFAULT_SCRIPTS.keys())
    try:
        col = get_collection()
        if col:
            for doc in col.find({}, {"key": 1, "_id": 0}):
                all_keys.add(doc["key"])
    except:
        pass
    return JSONResponse({"keys": sorted(list(all_keys))})


@router.get("/preview/{key}")
async def api_preview_script(
    key: str,
    name: str = "Tarun",
    time: str = "14 May 2026 at 05:00 PM"
):
    """Preview script with sample variables applied."""
    text = get_script(key, {"name": name, "time": time, "company": "Binjwa IT Solutions"})
    return JSONResponse({"key": key, "preview": text})


@router.get("/{key}")
async def api_get_script(key: str):
    """Get a single script by key."""
    try:
        col = get_collection()
        if col:
            doc = col.find_one({"key": key}, {"_id": 0})
            if doc:
                return JSONResponse({**doc, "source": "custom"})
    except:
        pass

    default = DEFAULT_SCRIPTS.get(key)
    if default:
        return JSONResponse({
            "key": key,
            "script_text": default["text"],
            "description": default["description"],
            "source": "default",
            "updated_at": None
        })

    return JSONResponse({"error": f"Script '{key}' not found."}, status_code=404)


@router.post("/")
async def api_set_script(data: dict):
    """
    Create or update a script.
    Body: { "key": "ivr_greeting", "script_text": "Hello {name}...", "description": "..." }
    """
    key  = data.get("key", "").strip()
    text = data.get("script_text", "").strip()
    desc = data.get("description", "").strip()

    if not key or not text:
        return JSONResponse(
            {"error": "Both 'key' and 'script_text' are required."},
            status_code=400
        )

    if set_script(key, text, desc):
        print(f"✅ [ScriptManager] Script '{key}' saved via API.")
        return JSONResponse({"status": "saved", "key": key})
    return JSONResponse({"error": "Failed to save. Check MongoDB connection."}, status_code=500)


@router.delete("/{key}")
async def api_delete_script(key: str):
    """Delete a custom script (reverts to built-in default)."""
    if delete_script(key):
        print(f"🗑️ [ScriptManager] Script '{key}' deleted. Reverted to default.")
        return JSONResponse({
            "status": "deleted",
            "key": key,
            "note": "Reverted to default script."
        })
    return JSONResponse({"error": "Failed to delete."}, status_code=500)
