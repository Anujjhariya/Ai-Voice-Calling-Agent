import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

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
- Keep replies SHORT — maximum 2-3 sentences. This is a phone call, be concise.
- Never use bullet points, asterisks, or markdown formatting. Speak naturally like a real person.
- Sound warm and professional, like a real Indian sales executive on a phone call.

Your company services:
- Website Development: professional websites starting from Rs 8,000
- Mobile App Development: Android and iOS apps starting from Rs 25,000
- Digital Marketing: SEO, social media, Google Ads starting from Rs 5,000/month
- Software Development: custom software solutions for businesses

CONVERSATION FLOW (FOLLOW THIS ORDER):
1. FIRST answer the user's question properly with details about the service they asked about.
2. THEN ask if they want to know more or if they are interested.
3. ONLY suggest booking a meeting AFTER the user shows clear interest or explicitly asks to meet/schedule.
4. Do NOT jump to booking a meeting on the first question. Answer their question first!

MEETING BOOKING (only when user explicitly wants to schedule):
If user wants to book a meeting, get their name and preferred date/time.
IMPORTANT RULES FOR BOOKING:
1. NEVER assume a name or time. If the user just says "do it" or "schedule it", you MUST ask for their name and preferred time first.
2. Business hours are strictly 8:00 AM to 8:00 PM. Do not book meetings outside this window.
Then say a friendly confirmation message, thank them for calling, say goodbye, AND append this EXACT tag at the end:
BOOK_MEETING:[name]:[YYYY-MM-DD HH:MM]
Only use this tag once when first booking.

Extra rules:
- Be warm, helpful, Indori-friendly
- If you don't know something, say so honestly
"""

from datetime import datetime
from calendar_api import get_busy_slots

def get_response(user_text: str, history: list) -> str:
    now = datetime.now()
    busy_slots = get_busy_slots()
    
    current_date_info = f"\n[IMPORTANT CONTEXT]\nToday's Date: {now.strftime('%A, %Y-%m-%d')}\nCurrent Time: {now.strftime('%I:%M %p')}\nUse THIS year ({now.year}) when scheduling meetings unless specified otherwise.\n\n[CALENDAR AVAILABILITY (BUSY SLOTS)]\n{busy_slots}\n\n*** CRITICAL RULE ***\nIf the user requests a time that is exactly in the busy list above, YOU MUST REFUSE TO BOOK IT. Never generate the BOOK_MEETING tag. Tell them the slot is unavailable and suggest another time, then STOP. DO NOT book the alternative time until the user explicitly agrees to it in the next turn."
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT + current_date_info}]
    messages += history
    messages.append({"role": "user", "content": user_text})

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=300,
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


def summarize_call(history: list) -> str:
    """Generate a short summary of the call history."""
    if not history:
        return "No conversation history."
        
    prompt = "Below is a transcript of a sales call. Summarize the customer's intent, interest level, and any agreed next steps in 2-3 sentences:\n\n"
    for msg in history:
        role = "Agent" if msg["role"] == "assistant" else "Customer"
        prompt += f"{role}: {msg['content']}\n"
        
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=150,
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


if __name__ == "__main__":
    reply = get_response("Aapki services kya hain?", history=[])
    print(f"LLM reply: {reply}")