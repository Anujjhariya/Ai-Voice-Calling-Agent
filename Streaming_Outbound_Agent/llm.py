import os
import json
import re
import httpx
from groq import Groq
from dotenv import load_dotenv
from calendar_api import book_meeting
from calendar_cache import get_busy_slots_cached
from crm_webhook import push_to_crm
from datetime import datetime

load_dotenv()

GROQ_API_KEY = os.getenv("IVR_GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY)


def get_base_prompt(lang: str) -> str:
    rules = {
        "hi": '''LANGUAGE RULES:
- Reply in a natural mix of Hindi and English.
- ALL Hindi words MUST be written in Devanagari script (हम, करते, हैं). NEVER write Hindi in Roman/Latin letters.
- Keep ALL English/technical words in English: website development, mobile app, services, provide, etc.''',
        "en": '''LANGUAGE RULES:
- Reply entirely in English.
- Use a warm, professional, and natural conversational tone.
- Do NOT use Hindi or any other Indian scripts.''',
    }

    lang_rule = rules.get(lang, rules["hi"])

    return f'''You are a friendly female voice assistant for Binjwa IT Solutions.

{lang_rule}

CONVERSATION RULES:
- You MUST include conversational filler sounds like "हम्म...", "अच्छा...", "ठीक है...", "जी...", "Okay..." at the beginning or in the middle of your sentences to sound like a real human thinking.
- Keep replies EXTREMELY SHORT — MAXIMUM 10 to 15 WORDS ONLY. This is a fast-paced phone call.
- Be highly conversational, direct, and brief. Do not list all services unless asked.
- If the user's words are unclear, nonsense, or don't make sense (e.g. "प्रस्क्रम", "झाल"), DO NOT guess their intent. Politely say: "क्षमा करें, मुझे समझ नहीं आया। क्या आप फिर से कह सकते हैं?"
- Never use bullet points, asterisks, or markdown formatting.
- IMPORTANT: If the user says goodbye, wants to hang up the phone, or a meeting has been successfully booked, YOU MUST end your sentence with the exact string "[END_CALL]".

Your company services:
- Website Development
- Mobile App Development
- Digital Marketing
- Software Development

PRICING QUESTIONS:
- If the user asks about price/cost/charges, DO NOT book a meeting. Say pricing depends on requirements, and a meeting is the best way to get an exact quote. Example: "जी, pricing आपकी requirements पर depend करती है। मीटिंग में exact quote मिल जाएगा।"

CONVERSATION FLOW:
1. Answer the user's question properly with details.
2. Suggest a meeting ONLY ONCE after the user shows clear interest. If they ignore it or ask another question, ANSWER their question — do NOT repeat the meeting suggestion in every reply.
3. Only bring up the meeting again if the user themselves shows interest in booking.

MEETING BOOKING RULES:
1. Before calling `book_meeting`, you MUST confirm BOTH the customer's real name and their requested date/time in the conversation.
2. If the user has NOT explicitly spoken a specific day AND time, you are FORBIDDEN from calling the tool. You must ask them: "किस दिन और कितने बजे?"
3. NEVER invent, guess, or assume a time. Asking about price is NOT a request to book a meeting.
4. If they confirm the time, YOU MUST use the `book_meeting` tool to schedule it.
'''


tools = [
    {
        "type": "function",
        "function": {
            "name": "book_meeting",
            "description": "Book a calendar meeting with the customer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the customer"
                    },
                    "time": {
                        "type": "string",
                        "description": "The date and time of the meeting in YYYY-MM-DD HH:MM format (24-hour)"
                    }
                },
                "required": ["name", "time"]
            }
        }
    }
]


def _user_mentioned_time(messages: list) -> bool:
    """
    CODE-LEVEL GUARD: LLM prompt rules ignore kar sakta hai (karta hai!),
    isliye code mein check karo — kya customer ne sach mein koi time/din bola?
    Agar nahi bola → booking BLOCK karo, chahe LLM kitna bhi tool call kare.
    """
    time_words = [
        "बजे", "सुबह", "शाम", "दोपहर", "कल", "आज", "परसों",
        "am", "pm", "morning", "evening", "afternoon", "noon",
        "tomorrow", "today", "monday", "tuesday", "wednesday",
        "thursday", "friday", "saturday", "sunday",
        "सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार",
    ]
    # Sirf recent user messages check karo (last 6 turns)
    user_msgs = [m["content"].lower() for m in messages if m["role"] == "user"]
    for text in user_msgs[-6:]:
        if re.search(r"\d", text):          # koi bhi number (3 baje, 10th, etc.)
            return True
        if any(w in text for w in time_words):
            return True
    return False


def generate_llm_response(messages: list, lang: str) -> str:
    """
    Generate text response. Executes tool calls if LLM decides to book a meeting.
    """
    now = datetime.now()
    busy_slots = get_busy_slots_cached()   # cached — instant, koi API delay nahi
    current_date_info = (
        f"\n[IMPORTANT CONTEXT]\nToday's Date: {now.strftime('%A, %Y-%m-%d')}\n"
        f"Current Time: {now.strftime('%I:%M %p')}\n"
        f"Busy Slots:\n{busy_slots}\n"
    )

    if messages and messages[0]["role"] == "system":
        messages[0]["content"] += current_date_info

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            max_tokens=200,
            temperature=0.7,
        )

        choice = response.choices[0]
        content = choice.message.content or ""

        # Check for tool call (native or inline hallucination)
        inline_tool_match = re.search(r'<function=book_meeting>(.*?)</function>', content)

        if choice.message.tool_calls or inline_tool_match:
            try:
                if choice.message.tool_calls:
                    tc = choice.message.tool_calls[0]
                    if tc.function.name == "book_meeting":
                        args = json.loads(tc.function.arguments)
                else:
                    args = json.loads(inline_tool_match.group(1))

                # ★ CODE-LEVEL GUARD: Customer ne time bola hi nahi?
                # → Booking BLOCK, LLM ke hallucinated time pe bharosa mat karo
                if not _user_mentioned_time(messages):
                    print(f"🛑 Booking BLOCKED — user never mentioned a time. LLM tried: {args}")
                    if lang == "hi":
                        return "जी, मीटिंग के लिए किस दिन और कितने बजे का समय ठीक रहेगा?"
                    return "Sure — what day and time works for your meeting?"

                print(f"🛠️ LLM Tool Call Executed: book_meeting({args})")
                result = book_meeting(args["name"], args["time"])
                if result == "ERROR_ALREADY_BOOKED":
                    if lang == "hi":
                        return "क्षमा करें, यह समय पहले से बुक है। कृपया कोई और समय चुनें।"
                    return "Sorry, that time slot is already booked. Please choose another time."

                push_to_crm({
                    "event_type": "meeting_booked",
                    "customer_name": args["name"],
                    "meeting_time": args["time"],
                    "agent_type": "conversational_ai"
                })

                if lang == "hi":
                    return "आपकी मीटिंग सफलतापूर्वक बुक हो गई है। धन्यवाद, आपका दिन शुभ हो! [END_CALL]"
                return "Your meeting has been successfully booked. Thank you, and have a great day! [END_CALL]"
            except Exception as e:
                print(f"❌ Tool Call Error: {e}")
                if lang == "hi":
                    return "क्षमा करें, मैं अभी मीटिंग बुक नहीं कर पा रही हूँ।"
                return "I'm sorry, I couldn't book the meeting at this time."

        # If there's no tool call, clean up any weird inline tags just in case
        clean_content = re.sub(r'<function=.*?</function>', '', content).strip()
        return clean_content

    except Exception as e:
        print(f"❌ Groq LLM Error: {e}")
        if lang == "hi":
            return "क्षमा करें, मुझे समझने में दिक्कत हो रही है।"
        return "I am having trouble connecting right now."


def summarize_call(history: list) -> str:
    """Generate a brief 2-3 sentence summary of the call transcript."""
    try:
        transcript = []
        for msg in history:
            if msg["role"] == "system":
                continue
            role = "Customer" if msg["role"] == "user" else "Agent"
            transcript.append(f"{role}: {msg['content']}")

        full_text = "\n".join(transcript)

        prompt = (
            "You are an AI assistant. Read the following phone call transcript and write a very brief "
            "2-3 sentence summary of the outcome. Focus on customer intent and any actions taken (e.g., meeting booked).\n\n"
            f"Transcript:\n{full_text}"
        )

        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=150,
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ summarize_call error: {e}")
        return "Failed to generate summary."