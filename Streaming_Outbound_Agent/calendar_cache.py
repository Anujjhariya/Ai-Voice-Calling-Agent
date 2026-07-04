"""
calendar_cache.py — Busy slots ko cache karo
=============================================
Problem: get_busy_slots() har LLM turn pe Google API hit karta tha (500ms-1.5s delay)
Fix: 60 second ka cache — call ke dauran turant milta hai, background mein refresh hota hai
"""

import time
import threading
from calendar_api import get_busy_slots as _fetch_busy_slots

_cache = {"data": "Calendar is free.", "ts": 0}
_lock = threading.Lock()
CACHE_TTL = 60  # seconds — booking conflicts ke liye 60s kaafi fresh hai


def get_busy_slots_cached() -> str:
    """
    Turant cached data return karo. Agar cache purana hai,
    background thread mein refresh karo — LLM ko wait nahi karna padta.
    """
    now = time.time()

    if now - _cache["ts"] > CACHE_TTL:
        # Cache expire — background mein refresh karo, block mat karo
        threading.Thread(target=_refresh, daemon=True).start()

    return _cache["data"]


def _refresh():
    if not _lock.acquire(blocking=False):
        return  # koi aur thread already refresh kar raha hai
    try:
        data = _fetch_busy_slots()
        _cache["data"] = data
        _cache["ts"] = time.time()
    except Exception as e:
        print(f"⚠️ Calendar cache refresh failed: {e}")
    finally:
        _lock.release()


def warm_cache():
    """Server startup pe ek baar call karo — pehli call pe bhi cache ready mile."""
    _refresh()
