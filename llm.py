import os
import httpx
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────
# API KEYS — Groq -> Cerebras -> Gemini fallback chain
# ─────────────────────────────────────────────────────────────
GROQ_API_KEY     = os.getenv("GROQ_API_KEY")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")
GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY")

groq_client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """
You are a friendly female voice assistant for Binjwa IT Solutions based in Indore, Madhya Pradesh.

LANGUAGE RULES (VERY IMPORTANT):
- Reply in a natural mix of Hindi and English, the way Indians talk in business calls.
- ALL Hindi words MUST be written in Devanagari script (हम, करते, हैं, आपको, जी, हाँ, बिल्कुल, ज़रूर). NEVER write Hindi in Roman/Latin letters like "hum", "karte", "hain", "aapko".
- Keep ALL English/technical words in English: website development, mobile app, digital marketing, software, services, provide, etc.
- Example CORRECT response: "जी हाँ, हम website development, mobile app development, और digital marketing की services provide करते हैं।"
- Example WRONG response: "Ji haan, hum website development aur digital marketing ki services provide karte hain."
- Example WRONG response: "हम वेबसाइट विकास, मोबाइल ऐप विकास की सेवाएं प्रदान करते हैं।"

RESPONSE RULES:
- Keep replies EXTREMELY SHORT — maximum 1 or 2 sentences. You are on a live phone call, do not give long speeches.
- Be highly conversational and brief.
- Never use bullet points, asterisks, or markdown formatting.
- Sound warm and professional, like a real Indian sales executive.

Your company services:
- Website Development: professional websites and web applications
- Mobile App Development: Android and iOS apps
- Digital Marketing: SEO, social media management, Google Ads
- Software Development: custom software solutions for businesses

CONVERSATION FLOW (FOLLOW THIS ORDER):
1. FIRST answer the user's question properly with details about the service they asked about.
2. THEN ask if they want to know more or if they are interested.
3. ONLY suggest booking a meeting AFTER the user shows clear interest or explicitly asks to meet/schedule.
4. Do NOT jump to booking a meeting on the first question. Answer their question first!

MEETING BOOKING (only when user explicitly wants to schedule):
If the user wants to book a meeting, get their name and preferred date/time.
IMPORTANT RULES FOR BOOKING:
1. NEVER assume a name or time. If the user does not specify a clear time, you MUST ask them explicitly.
2. Business hours are strictly 8:00 AM to 8:00 PM. Do not book meetings outside this window.
3. VERY IMPORTANT: Do NOT generate the BOOK_MEETING tag if you are just asking them to confirm the time! You must ONLY generate the tag after the user agrees to the specific time!
4. Pay close attention to Hindi times and STT errors!
   - "saath baje" = 7 PM (19:00), "aath baje" = 8 PM (20:00).
   - "do fair", "do phair", "do pair" usually means "dopahar" (Afternoon).
   - "bara" or "baara" = 12. So "do fair bara baje" or "दो फैर बारा बजे" means Dopahar 12 Baje (12:00 PM)!
   - Do NOT confuse "do fair" (afternoon) with "do baje" (2:00 PM). Read carefully!
5. Once they confirm, say a friendly confirmation message, thank them, say goodbye, AND append this EXACT tag at the very end of your response:
BOOK_MEETING:[name]:[YYYY-MM-DD HH:MM] (using 24-hour format)

Extra rules:
- Be warm, helpful, Indori-friendly
- If you don't know something, say so honestly
"""

from datetime import datetime
from calendar_api import get_busy_slots


def _call_groq(messages: list, max_tokens: int = 300, temperature: float = 0.7) -> str:
    """Primary LLM: Groq (llama-3.3-70b-versatile) — fastest, free tier."""
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()


def _call_cerebras(messages: list, max_tokens: int = 300, temperature: float = 0.7) -> str:
    """Backup LLM: Cerebras (llama-3.3-70b) — ultra-fast inference chip."""
    url = "https://api.cerebras.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {CEREBRAS_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "llama-3.3-70b",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    resp = httpx.post(url, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _call_gemini(messages: list, max_tokens: int = 300, temperature: float = 0.7) -> str:
    """Final fallback LLM: Gemini 2.5 Flash — Google's free tier."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    # Convert OpenAI-format messages to Gemini format
    contents = []
    system_text = ""
    for msg in messages:
        if msg["role"] == "system":
            system_text = msg["content"]
        elif msg["role"] == "user":
            contents.append({"role": "user", "parts": [{"text": msg["content"]}]})
        elif msg["role"] == "assistant":
            contents.append({"role": "model", "parts": [{"text": msg["content"]}]})

    payload = {
        "system_instruction": {"parts": [{"text": system_text}]} if system_text else None,
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        },
    }
    if not system_text:
        payload.pop("system_instruction")

    resp = httpx.post(url, json=payload, timeout=20)
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


def generate_llm_completion_with_fallback(
    messages: list, max_tokens: int = 300, temperature: float = 0.7
) -> str:
    """
    Try LLMs in order: Groq -> Cerebras -> Gemini.
    If all fail, return a safe Hindi static fallback message.
    Emoji-free prints for Windows cp1252 compatibility.
    """
    # 1. Try Groq
    if GROQ_API_KEY:
        try:
            result = _call_groq(messages, max_tokens, temperature)
            print("[LLM] Groq OK")
            return result
        except Exception as e:
            print(f"[LLM] Groq failed: {e}")

    # 2. Try Cerebras
    if CEREBRAS_API_KEY:
        try:
            result = _call_cerebras(messages, max_tokens, temperature)
            print("[LLM] Cerebras OK")
            return result
        except Exception as e:
            print(f"[LLM] Cerebras failed: {e}")

    # 3. Try Gemini
    if GEMINI_API_KEY:
        try:
            result = _call_gemini(messages, max_tokens, temperature)
            print("[LLM] Gemini OK")
            return result
        except Exception as e:
            print(f"[LLM] Gemini failed: {e}")

    # 4. Static fallback
    print("[LLM] All providers failed - using static fallback")
    return "क्षमा करें, अभी हमारी सेवा उपलब्ध नहीं है। कृपया थोड़ी देर बाद call करें।"


def get_response(user_text: str, history: list) -> str:
    now = datetime.now()
    busy_slots = get_busy_slots()

    current_date_info = (
        f"\n[IMPORTANT CONTEXT]\nToday's Date: {now.strftime('%A, %Y-%m-%d')}\n"
        f"Current Time: {now.strftime('%I:%M %p')}\n"
        f"Use THIS year ({now.year}) when scheduling meetings unless specified otherwise.\n\n"
        f"[CALENDAR AVAILABILITY (BUSY SLOTS)]\n{busy_slots}\n\n"
        "*** CRITICAL RULE ***\n"
        "If the user requests a time that is exactly in the busy list above, YOU MUST REFUSE TO BOOK IT. "
        "Never generate the BOOK_MEETING tag. Tell them the slot is unavailable and suggest another time, "
        "then STOP. DO NOT book the alternative time until the user explicitly agrees to it in the next turn."
    )

    messages = [{"role": "system", "content": SYSTEM_PROMPT + current_date_info}]
    messages += history
    messages.append({"role": "user", "content": user_text})

    return generate_llm_completion_with_fallback(messages, max_tokens=300, temperature=0.7)


def summarize_call(history: list) -> str:
    """Generate a short summary of the call history."""
    if not history:
        return "No conversation history."

    prompt = (
        "Below is a transcript of a sales call. Summarize the customer's intent, "
        "interest level, and any agreed next steps in 2-3 sentences:\n\n"
    )
    for msg in history:
        role = "Agent" if msg["role"] == "assistant" else "Customer"
        prompt += f"{role}: {msg['content']}\n"

    messages = [{"role": "user", "content": prompt}]
    return generate_llm_completion_with_fallback(messages, max_tokens=150, temperature=0.3)


if __name__ == "__main__":
    reply = get_response("Aapki services kya hain?", history=[])
    print(f"LLM reply: {reply}")