# 🤖 Agent Outbound Calling System

Your AI agent can now **initiate calls to customers** and have natural conversations with emotional voices!

---

## 📋 System Overview

| Component | Purpose |
|-----------|---------|
| **agent_outbound.py** | Main agent calling logic (NEW!) |
| **test_agent_outbound_call.py** | Test script to trigger calls |
| **main_dynamic_vobiz.py** | Updated to include agent router |

---

## 🚀 Quick Start

### Step 1: Start Your Server
```bash
cd Vobiz_Working_Project
python main_dynamic_vobiz.py
```

Wait for startup message.

### Step 2: Trigger an Agent Call
```bash
# Happy greeting (English)
python test_agent_outbound_call.py --phone 918319688692 --name "Anuj" --emotion happy

# Professional tone (Hindi)
python test_agent_outbound_call.py --phone 919876543210 --name "राज" --emotion professional

# Excited tone (English)
python test_agent_outbound_call.py --phone 919999999999 --name "Sarah" --emotion excited
```

### Step 3: Answer the Call!
Your phone will ring and the agent will:
- 🎭 **Greet** with emotional voice
- 👂 **Listen** to your response
- 🤖 **Think** using AI/LLM
- 💬 **Respond** naturally
- 🔄 **Repeat** the conversation

---

## 🎭 Available Emotions

```
happy           → Upbeat, positive, enthusiastic
professional    → Formal, business-like, serious
excited         → Very enthusiastic, energetic
warm            → Friendly, caring, supportive
conversational  → Neutral, natural, friendly (default)
```

---

## 🗣️ Supported Languages

```
en  → English (Indian accent)
hi  → Hindi (Devanagari)
mr  → Marathi
gu  → Gujarati
pa  → Punjabi
```

---

## 📞 How the Conversation Works

```
1️⃣ Agent calls customer phone number
2️⃣ Customer picks up
3️⃣ Agent greets with emotion (e.g., "Hello! This is an AI assistant...")
4️⃣ Vobiz gathers customer's speech response
5️⃣ Agent's LLM processes the response
6️⃣ Agent replies with emotional voice
7️⃣ Loop continues until customer says "bye" or timeout

📅 Special: If customer mentions "meeting", "schedule", or "appointment"
   Agent automatically offers to book a meeting
```

---

## 📊 Monitor Active Calls

### List All Active Sessions
```bash
python test_agent_outbound_call.py --list
```

Output:
```
🤖 Active Agent Call Sessions: 2

  📞 Anuj
     Emotion: happy
     Language: en
     Duration: 45.2s
     Messages: 8

  📞 Sarah
     Emotion: professional
     Language: hi
     Duration: 23.1s
     Messages: 4
```

### Get Session Details (via API)
```bash
curl http://127.0.0.1:8000/agent/sessions
curl http://127.0.0.1:8000/agent/session/{call_uuid}
```

---

## 💻 Advanced Usage

### Use in Your Code

```python
import requests
import os

BASE_URL = os.getenv("IVR_BASE_URL")
AUTH_ID = os.getenv("IVR_VOBIZ_AUTH_ID")
AUTH_TOKEN = os.getenv("IVR_VOBIZ_AUTH_TOKEN")
VOBIZ_PHONE = os.getenv("IVR_VOBIZ_PHONE_NUMBER")

def trigger_agent_call(phone, name, emotion="happy", lang="en"):
    """Trigger agent to call a customer"""
    payload = {
        "from": VOBIZ_PHONE,
        "to": phone,
        "answer_url": f"{BASE_URL}/agent/outbound_call?name={name}&emotion={emotion}&lang={lang}",
        "answer_method": "GET",
        "hangup_url": f"{BASE_URL}/agent/call_ended?name={name}",
        "hangup_method": "POST",
    }
    
    response = requests.post(
        f"https://api.vobiz.ai/api/v1/Account/{AUTH_ID}/Call/",
        json=payload,
        headers={
            "X-Auth-ID": AUTH_ID,
            "X-Auth-Token": AUTH_TOKEN,
            "Content-Type": "application/json"
        }
    )
    
    if response.status_code in [200, 201, 202]:
        call_uuid = response.json().get("call_uuid")
        return call_uuid
    else:
        print(f"Error: {response.text}")
        return None

# Make the call
call_uuid = trigger_agent_call(
    phone="918319688692",
    name="Anuj",
    emotion="happy",
    lang="en"
)
print(f"Call initiated: {call_uuid}")
```

---

## 🔄 What the Agent Does

### When Customer Speaks
1. Vobiz records customer's speech
2. **Groq Whisper** transcribes it to text
3. **LLM (Groq Llama)** generates response
4. **Murf.ai** converts response to emotional speech
5. Agent plays speech to customer
6. Loop continues

### When Customer Says "Book/Schedule/Meeting"
1. Agent recognizes booking intent
2. Agent asks: "What time works for you?"
3. Customer provides time
4. **LLM** parses the time
5. **Google Calendar API** checks availability
6. **Book meeting** if available
7. Agent confirms and says goodbye

### When Customer Says "Bye/Goodbye"
1. Agent recognizes end intent
2. Agent says: "Thank you for your time!"
3. Agent hangs up
4. Session logged and cleaned up

---

## 📁 File Structure

```
Vobiz_Working_Project/
├── main_dynamic_vobiz.py         ← Main server (UPDATED)
├── agent_outbound.py              ← Agent calling logic (NEW)
├── test_agent_outbound_call.py    ← Test script (UPDATED)
├── dynamic_ivr.py                 ← IVR logic (unchanged)
├── web_agent.py                   ← Web chat agent
├── tts.py                         ← Text-to-speech (emotional voices)
├── llm.py                         ← LLM responses
├── stt.py                         ← Speech recognition
└── calendar_api.py                ← Meeting booking
```

---

## 🔌 API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/agent/outbound_call` | GET/POST | Entry point when call is picked up |
| `/agent/handle_response` | POST | Process customer's voice response |
| `/agent/process_booking` | POST | Handle meeting booking |
| `/agent/call_ended` | POST | Clean up when call ends |
| `/agent/sessions` | GET | List all active sessions |
| `/agent/session/{call_uuid}` | GET | Get specific session details |

---

## 🎯 Use Cases

### 1. **Sales Outreach**
```bash
python test_agent_outbound_call.py --phone 918319688692 --name "Prospect Name" --emotion excited
```
Agent will pitch services with excited tone!

### 2. **Customer Support**
```bash
python test_agent_outbound_call.py --phone 918319688692 --name "Customer Name" --emotion warm
```
Agent will listen to issues with empathy!

### 3. **Appointment Booking**
```bash
python test_agent_outbound_call.py --phone 918319688692 --name "Anuj" --emotion professional
```
Agent will offer to schedule meetings!

### 4. **Multilingual Support**
```bash
# Call in Hindi
python test_agent_outbound_call.py --phone 919876543210 --name "राज" --emotion happy --lang hi

# Call in Gujarati
python test_agent_outbound_call.py --phone 919999999999 --name "पांडुरंग" --emotion professional --lang gu
```

---

## ⚙️ Troubleshooting

### Call Not Going Through
- ✅ Check Vobiz credentials in `.env`
- ✅ Check if you have account balance
- ✅ Check if phone number is correct
- ✅ Check if server is running on correct URL

### Agent Not Responding
- ✅ Check Groq API key
- ✅ Check LLM rate limits
- ✅ Check internet connection
- ✅ Check server logs

### Audio/Voice Issues
- ✅ Check Murf API key
- ✅ Check language code matches
- ✅ Check emotion is valid
- ✅ Check audio device on receiving end

---

## 📝 Example: Full Conversation

```
🤖 Agent: "Hello Anuj! This is an AI assistant from Binjwa IT Solutions. 
            How are you doing today?"

👤 Customer: "Hi, I'm good. I was interested in your web development services."

🤖 Agent: "That's great! We specialize in professional websites and web apps. 
           What kind of website are you looking for?"

👤 Customer: "I need an e-commerce site for my business."

🤖 Agent: "Perfect! E-commerce websites are our specialty. We create 
           secure, fast, and user-friendly online stores. Would you like 
           to schedule a meeting to discuss your requirements?"

👤 Customer: "Yes, that sounds good. Tomorrow at 2 PM?"

🤖 Agent: "Excellent! I've scheduled a meeting for tomorrow at 2 PM. 
           Our team will send you the details. Thank you for your time!"

[Call ends, meeting booked in calendar]
```

---

## 🚀 Next Steps

1. ✅ **Test basic calls** — Try different emotions
2. ✅ **Test multilingual** — Try different languages  
3. ✅ **Monitor sessions** — Use `/agent/sessions` endpoint
4. ✅ **Integrate with CRM** — Link call UUIDs to contacts
5. ✅ **Scale campaigns** — Call multiple prospects at once

---

Enjoy your agent calling system! 🎉
