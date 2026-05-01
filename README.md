# 🤖 AI Voice Calling Agent

An AI-powered voice calling agent for **Binjwa IT Solutions** that makes outbound sales calls, answers questions about services, and books meetings on Google Calendar — all in natural Hinglish (Hindi + English).

## ✨ Features

- **Real-time Voice Conversations** — Bidirectional WebSocket audio streaming
- **Natural Hinglish Speech** — Speaks in a mix of Hindi (Devanagari) and English, like a real Indian sales executive
- **Instant Greeting** — Pre-cached greeting audio for zero-delay call start
- **Streaming TTS** — Audio plays within ~130ms using Murf Falcon streaming
- **Voice Activity Detection (VAD)** — Detects when the user stops speaking using RMS energy
- **Meeting Booking** — Automatically books meetings on Google Calendar
- **Twilio + Exotel Support** — Works with both telephony providers

## 🏗️ Architecture

```
Phone Call → Twilio/Exotel WebSocket → FastAPI Server
                                          ↓
                                    Audio (ULAW/PCM)
                                          ↓
                                   Groq Whisper (STT)
                                          ↓
                                   Groq Llama 3.3 (LLM)
                                          ↓
                                   Murf Falcon (TTS)
                                          ↓
                                   Audio Stream → Caller
```

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| **Server** | FastAPI + Uvicorn |
| **STT** | Groq Whisper Large v3 Turbo |
| **LLM** | Groq Llama 3.3 70B |
| **TTS** | Murf AI Falcon (India endpoint) |
| **Telephony** | Twilio / Exotel |
| **Calendar** | Google Calendar API v3 |

## 📁 Project Structure

```
├── main.py              # Twilio WebSocket server (primary)
├── main_copy.py         # Exotel WebSocket server (alternative)
├── tts.py               # Murf Falcon TTS (batch + streaming)
├── stt.py               # Groq Whisper speech-to-text
├── llm.py               # Groq Llama 3.3 LLM with Hinglish prompt
├── calendar_api.py      # Google Calendar meeting booking
├── lang_detect.py       # Language detection
├── outbound_twillio.py  # Twilio outbound call trigger
├── outbound.py          # Exotel outbound call trigger
├── .env.example         # Environment variables template
└── requirements.txt     # Python dependencies
```

## 🚀 Setup

### 1. Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/ai-voice-calling-agent.git
cd ai-voice-calling-agent
python -m venv .venv
.venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
copy .env.example .env
# Edit .env with your actual API keys
```

**Required API Keys:**
- [Groq](https://console.groq.com) — Free tier available (STT + LLM)
- [Murf AI](https://murf.ai/api) — $10 free credit (TTS)
- [Twilio](https://twilio.com) — Trial account available (Telephony)

### 3. Google Calendar Setup (Optional)

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Enable **Google Calendar API**
3. Create **OAuth 2.0 Client ID** (Desktop App)
4. Download as `credentials.json` and place in project root
5. Run authorization:

```bash
python calendar_api.py
```

### 4. Start the Server

```bash
# Start ngrok tunnel
ngrok http 8000

# Update BASE_URL in .env with your ngrok URL

# Start the server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. Make a Call

```bash
python outbound_twillio.py
```

## ⚙️ Configuration

### Voice Settings (tts.py)
- **Voice**: Sunaina (Hindi female, Conversational style)
- **Sample Rate**: 8000 Hz
- **Format**: WAV → PCM → ULAW (for Twilio)

### VAD Settings (main.py)
- **Silence Threshold**: 300 RMS
- **Silence Cutoff**: 40 chunks (~0.8s of silence)
- **Recording Duration**: 7 seconds max

## 📄 License

MIT License

## 👨‍💻 Author

Binjwa IT Solutions, Indore, Madhya Pradesh
