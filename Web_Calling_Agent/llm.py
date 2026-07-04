import os
import httpx
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────
# API KEYS — Groq -> Cerebras -> Gemini fallback chain
# Uses IVR_ prefix as per Vobiz_Working_Project .env convention
# ─────────────────────────────────────────────────────────────
GROQ_API_KEY     = os.getenv("IVR_GROQ_API_KEY")
CEREBRAS_API_KEY = os.getenv("IVR_CEREBRAS_API_KEY")
GEMINI_API_KEY   = os.getenv("IVR_GEMINI_API_KEY")

groq_client = Groq(api_key=GROQ_API_KEY)
def get_base_prompt(lang: str) -> str:
    rules = {
        "hi": '''LANGUAGE RULES (VERY IMPORTANT):
- Reply in a natural mix of Hindi and English.
- ALL Hindi words MUST be written in Devanagari script (हम, करते, हैं). NEVER write Hindi in Roman/Latin letters.
- Keep ALL English/technical words in English: website development, mobile app, services, provide, etc.
- Example CORRECT response: "जी हाँ, हम website development की services provide करते हैं।"''',
        "en": '''LANGUAGE RULES (VERY IMPORTANT):
- Reply entirely in English.
- Use a warm, professional, and natural conversational tone.
- Do NOT use Hindi or any other Indian scripts.''',
        "mr": '''LANGUAGE RULES (VERY IMPORTANT):
- Reply in Marathi.
- ALL Marathi words MUST be written in Devanagari script.
- Keep English/technical words in English (e.g., website development, digital marketing).''',
        "gu": '''LANGUAGE RULES (VERY IMPORTANT):
- Reply in Gujarati.
- ALL Gujarati words MUST be written in Gujarati script.
- Keep English/technical words in English.''',
        "pa": '''LANGUAGE RULES (VERY IMPORTANT):
- Reply in Punjabi.
- ALL Punjabi words MUST be written in Gurmukhi script.
- Keep English/technical words in English.'''
    }
    
    lang_rule = rules.get(lang, rules["hi"])
    
    return f'''You are a friendly female voice assistant for Binjwa IT Solutions.

{lang_rule}

RESPONSE RULES:
- Keep replies EXTREMELY SHORT — maximum 1 or 2 sentences. You are on a live phone call, do not give long speeches.
- Be highly conversational and brief.
- Never use bullet points, asterisks, or markdown formatting.
- Sound warm and professional.

Your company services:
- Website Development: professional websites and web applications
- Mobile App Development: Android and iOS apps
- Digital Marketing: SEO, social media management, Google Ads
- Software Development: custom software solutions for businesses

CONVERSATION FLOW (FOLLOW THIS ORDER):
1. FIRST answer the user's question properly with details about the service they asked about.
2. THEN ask if they want to know more or if they are interested.
3. ONLY suggest booking a meeting AFTER the user shows clear interest or explicitly asks to meet/schedule.

MEETING BOOKING (only when user explicitly wants to schedule):
If the user wants to book a meeting, get their name and preferred date/time.
IMPORTANT RULES FOR BOOKING:
1. NEVER assume a name or time. Ask them explicitly.
2. Business hours are strictly 8:00 AM to 8:00 PM.
3. VERY IMPORTANT: Do NOT generate the BOOK_MEETING tag if you are just asking them to confirm the time!
4. Once they confirm, say a friendly confirmation message, thank them, say goodbye, AND append this EXACT tag at the very end of your response:
BOOK_MEETING:[name]:[YYYY-MM-DD HH:MM] (using 24-hour format)
'''

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


def get_response(user_text: str, history: list, context: dict = None, lang: str = "hi") -> str:
    now = datetime.now()
    busy_slots = get_busy_slots()

    # Determine site title
    site_title = "Binjwa IT Solutions"
    if context and context.get("title"):
        raw_title = context.get("title", "")
        for suffix in [" - Home", " - Welcome", " | Website", " - AI Assistant", " - AI Voice Assistant"]:
            if raw_title.endswith(suffix):
                raw_title = raw_title[:-len(suffix)]
        site_title = raw_title.strip()

    # Build base language rules
    base_prompt = get_base_prompt(lang)

    # Build dynamic prompt depending on whether we have external website content
    if context and (context.get("bodyText") or context.get("description")):
        body_text = context.get("bodyText", "")
        description = context.get("description", "")
        url = context.get("url", "")
        
        # Inject context into the language-aware prompt
        dynamic_prompt = f"""{base_prompt}

[WEBSITE CONTEXT & SERVICES]
You are assisting a user browsing this website: {url}
Website Description: {description}
Webpage Content Snippet:
\"\"\"
{body_text}
\"\"\"

Answer the user's questions about the website, company, products, and services using the website content provided above. Always prioritize the information on the webpage. If the user asks about services/products mentioned on the page (like AI services or consulting), explain them enthusiastically.
"""
    else:
        dynamic_prompt = base_prompt

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

    messages = [{"role": "system", "content": dynamic_prompt + current_date_info}]
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