# 🎭 Emotional Voice Guide

Your AI agent now supports **emotional voices**! Here's how to use them.

---

## 📚 Available Emotions

| Emotion | Description | Example Use |
|---------|-------------|------------|
| **Conversational** | Neutral, natural, friendly (default) | General responses |
| **Happy** | Upbeat, positive, enthusiastic | Greetings, good news |
| **Professional** | Formal, business-like, serious | Important information |
| **Excited** | Very enthusiastic, energetic | Special offers, achievements |
| **Warm** | Friendly, caring, supportive | Customer support |
| **Friendly** | Approachable, open | Casual interactions |
| **Casual** | Relaxed, informal | Friendly chat |
| **Sad** | Mournful, concerned | Apologizing, bad news |
| **Concerned** | Worried, serious | Issues, problems |
| **Angry** | Frustrated, stern | (Use sparingly) |

---

## 🚀 Quick Start — Test Emotions Now

### Option 1: Test via Python Script
```bash
# Make sure the server is running first
python main_dynamic_vobiz.py

# In another terminal, trigger a call with specific emotion
python test_emotions.py happy en
python test_emotions.py professional en
python test_emotions.py excited en_male
python test_emotions.py happy hi
```

### Option 2: Test Web Agent (with emotions)
The web agent now uses **HAPPY** emotion for all greetings to sound warm and welcoming.

---

## 💻 How to Use in Your Code

### 1. **Use Emotional Voice Codes Directly**

```python
from tts import generate_pcm

# English with different emotions
audio = await generate_pcm("Welcome!", "en_happy")
audio = await generate_pcm("Your meeting is confirmed", "en_professional")
audio = await generate_pcm("Great news!", "en_excited")

# Hindi with emotions
audio = await generate_pcm("नमस्ते!", "hi_happy")
audio = await generate_pcm("आपकी मीटिং तय है", "hi_professional")
```

### 2. **Pass Emotion as Separate Parameter**

```python
from tts import generate_pcm, generate_wav

# Phone call (PCM format)
audio = await generate_pcm(
    "Thank you for calling!", 
    lang_code="en",
    emotion="Happy"
)

# Web preview (WAV format)
audio = await generate_wav(
    "Let's get started!",
    lang_code="en",
    gender="female",
    emotion="Excited"
)
```

### 3. **Supported Voice Codes**

```
English voices:
  - "en"               → Conversational (default)
  - "en_happy"         → Happy tone
  - "en_professional"  → Professional tone
  - "en_male"          → Male voice, conversational
  - "en_male_excited"  → Male voice, excited

Hindi voices:
  - "hi"               → Conversational (default)
  - "hi_happy"         → Happy tone
  - "hi_professional"  → Professional tone
  - "hi_male"          → Male voice, conversational
  - "hi_male_excited"  → Male voice, excited

Other languages available but without emotion variants:
  - "gu" (Gujarati)
  - "bn" (Bengali)
  - "mr" (Marathi)
  - "pa" (Punjabi)
```

---

## 🎯 Real-World Examples

### Greeting (Use HAPPY)
```python
greeting = "Hello! Welcome to Binjwa IT Solutions. I'm excited to help!"
audio = await generate_pcm(greeting, "en_happy")
```

### Professional Updates (Use PROFESSIONAL)
```python
update = "Your appointment has been confirmed for tomorrow at 2 PM."
audio = await generate_pcm(update, "en_professional")
```

### Call to Action (Use EXCITED)
```python
cta = "Fantastic! You're eligible for our special discount!"
audio = await generate_pcm(cta, "en_male_excited")
```

### Support Responses (Use WARM)
```python
support = "I understand your concern. Let me help you resolve this."
audio = await generate_pcm(support, "en", emotion="Warm")
```

---

## 🔧 How It Works

The system automatically:
1. **Parses voice codes** like `"en_happy"` into base language (`"en"`) + emotion (`"Happy"`)
2. **Sends emotion to Murf.ai** as the `style` parameter
3. **Generates speech** with the requested emotional tone
4. **Returns audio** in your preferred format (PCM for calls, WAV for web)

---

## 📝 Recent Changes

✅ **Updated `tts.py`:**
- `generate_pcm()` now accepts emotion parameter
- `generate_wav()` now accepts emotion parameter
- Automatic emotion parsing from voice codes (e.g., `"en_happy"`)

✅ **Updated `main_dynamic_vobiz.py`:**
- Greeting now uses **HAPPY** emotion
- Sounds warm and welcoming on every call

✅ **Updated `web_agent.py`:**
- All web greetings now use **HAPPY** emotion

✅ **Added `test_emotions.py`:**
- Quick testing script to hear emotions in action

---

## 🎤 Current Setup

### Phone Calls (IVR)
- **Greeting**: Happy tone (warm welcome)
- **Agent responses**: Currently using default (Conversational)
- **You can customize**: Any response can use any emotion!

### Web Agent
- **Greetings**: Happy tone (all languages)
- **Chat responses**: Currently using default (Conversational)
- **You can customize**: Any response can use any emotion!

---

## 🚀 Next Steps

1. **Test emotions** using `test_emotions.py`
2. **Customize agent responses** to use emotions in `dynamic_ivr.py` or `web_agent.py`
3. **A/B test** different emotions to see what resonates best with callers
4. **Add more voice variants** to `VOICE_MAP` in `tts.py` as needed

---

## 📞 Example: Full Emotional Call Flow

```
Greeting (HAPPY):     "Hello! I'm so glad you called!"
Question (WARM):      "How can I help you today?"
Answer (PROFESSIONAL): "We offer website development services starting at $5,000."
CTA (EXCITED):        "Would you like to schedule a free consultation?"
Closing (WARM):       "Thank you for your time. Have a great day!"
```

---

## 💡 Pro Tips

- **First impression matters**: Use HAPPY for greetings
- **Build trust**: Use PROFESSIONAL for important details
- **Drive action**: Use EXCITED for special offers
- **Show empathy**: Use WARM for support and complaints
- **Consistency**: Pick 2-3 emotions and use them consistently
- **Test**: Always test with emotions before going live

---

Enjoy your emotional AI voice agent! 🎉
