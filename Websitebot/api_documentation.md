# Binjwa IT Solutions — Chatbot API Documentation

This document is for developers who want to build their own frontend UI and connect it to the Binjwa chatbot backend.

---

## Table of Contents

1. [Overview](#overview)
2. [Setup — Local (Development)](#setup--local-development)
3. [Setup — Docker (Production)](#setup--docker-production)
4. [Environment Variables](#environment-variables)
5. [API Endpoints](#api-endpoints)
   - [POST /chat](#post-chat)
   - [POST /upload-pdf](#post-upload-pdf)
6. [Integration Examples](#integration-examples)
   - [JavaScript (fetch)](#javascript-fetch)
   - [JavaScript (axios)](#javascript-axios)
   - [React Example](#react-example)
   - [cURL](#curl)
7. [CORS](#cors)
8. [Notes for Frontend Developers](#notes-for-frontend-developers)

---

## Overview

The backend is a Python Flask API that:
- Answers user questions based on uploaded PDF documents
- Detects whether the user is writing in English or Hinglish and responds accordingly
- Uses multiple AI models via OpenRouter (Claude, Gemini, LLaMA, Mistral) with automatic fallback
- Stores all chat history in MongoDB
- Supports runtime PDF uploads via API

You only need two endpoints to build a fully working chat UI:
- `POST /chat` — send a user message, get a bot response
- `POST /upload-pdf` — upload PDF files for the bot to learn from

---

## Setup — Local (Development)

### Prerequisites
- Python 3.10+
- MongoDB running locally on port 27017
- An OpenRouter API key (get one at https://openrouter.ai)

### Steps

```bash
# 1. Clone or copy the project
cd websitebot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create a .env file in the project root
echo OPENROUTER_API_KEY=your_key_here > .env

# 4. Run the server
python app.py
```

The server will start at `http://localhost:5000`.

PDFs placed in the `./pdfs/` folder are automatically loaded on startup.

---

## Setup — Docker (Production)

### Prerequisites
- Docker Desktop installed and running
- Docker Compose (included with Docker Desktop)

### Steps

```bash
# 1. Create a .env file in the project root
echo OPENROUTER_API_KEY=your_key_here > .env

# 2. Build and start all services (app + MongoDB)
docker compose up -d --build

# 3. Check that both containers are running
docker compose ps

# 4. View logs if needed
docker compose logs web
```

The app will be available at `http://your-server-ip:5000`.

To stop the services:
```bash
docker compose down
```

To change the port (e.g. expose on port 80):
Edit `docker-compose.yml` and change:
```yaml
ports:
  - "80:5000"
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes | Your OpenRouter API key |
| `MONGO_URI` | No | MongoDB connection string. Defaults to `mongodb://localhost:27017/`. In Docker this is set automatically to `mongodb://mongo:27017/`. |

---

## API Endpoints

### Base URL

- Local: `http://localhost:5000`
- Production: `http://your-server-ip:5000`

---

### POST /chat

Send a user message and receive a bot response.

**Endpoint:** `POST /chat`  
**Content-Type:** `application/json`

#### Request Body

```json
{
  "message": "What services does Binjwa IT Solutions provide?"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `message` | string | Yes | The user's question or message |

#### Success Response — `200 OK`

```json
{
  "success": true,
  "response": "Binjwa IT Solutions provides web development, mobile app development, CRM solutions, and digital marketing services."
}
```

#### Error Response — `400 Bad Request`

```json
{
  "error": "Message required"
}
```

#### Behaviour Notes

- If the question matches a predefined greeting (hi, hello, thanks, bye, etc.), the bot replies instantly without calling the AI.
- If no PDFs are loaded, the bot replies with a generic fallback message.
- If the message is completely unrelated to the business/documents, the bot replies: `"This question is outside our knowledge scope."`
- The bot auto-detects English vs Hinglish and replies in the same language.

---

### POST /upload-pdf

Upload one or more PDF files to the server. The bot immediately processes and learns from them.

**Endpoint:** `POST /upload-pdf`  
**Content-Type:** `multipart/form-data`

#### Request

Send the files using the field name `files`. Multiple files can be uploaded in a single request.

#### Success Response — `200 OK`

```json
{
  "success": true,
  "message": "PDFs uploaded and processed successfully!"
}
```

#### Error Responses — `400 Bad Request`

```json
{ "success": false, "error": "No file part" }
```
```json
{ "success": false, "error": "No files selected" }
```

---

## Integration Examples

### JavaScript (fetch)

```javascript
// Send a chat message
async function sendMessage(userMessage) {
  const response = await fetch("http://localhost:5000/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: userMessage })
  });

  const data = await response.json();
  return data.response; // the bot's reply
}

// Upload PDFs
async function uploadPDFs(fileList) {
  const formData = new FormData();
  for (const file of fileList) {
    formData.append("files", file);
  }

  const response = await fetch("http://localhost:5000/upload-pdf", {
    method: "POST",
    body: formData
  });

  return await response.json();
}
```

---

### JavaScript (axios)

```javascript
import axios from "axios";

const API_BASE = "http://localhost:5000";

// Send a chat message
async function sendMessage(userMessage) {
  const { data } = await axios.post(`${API_BASE}/chat`, {
    message: userMessage
  });
  return data.response;
}

// Upload PDFs
async function uploadPDFs(fileList) {
  const formData = new FormData();
  fileList.forEach(file => formData.append("files", file));

  const { data } = await axios.post(`${API_BASE}/upload-pdf`, formData);
  return data;
}
```

---

### React Example

```jsx
import { useState } from "react";

const API_BASE = "http://localhost:5000";

export default function Chat() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  async function send() {
    if (!input.trim()) return;

    const userMsg = input.trim();
    setInput("");
    setMessages(prev => [...prev, { role: "user", text: userMsg }]);
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMsg })
      });
      const data = await res.json();
      setMessages(prev => [...prev, { role: "bot", text: data.response }]);
    } catch {
      setMessages(prev => [...prev, { role: "bot", text: "Something went wrong." }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div>
        {messages.map((m, i) => (
          <div key={i} className={m.role}>
            {m.text}
          </div>
        ))}
        {loading && <div className="bot">Typing...</div>}
      </div>

      <input
        value={input}
        onChange={e => setInput(e.target.value)}
        onKeyDown={e => e.key === "Enter" && send()}
        placeholder="Ask a question..."
      />
      <button onClick={send}>Send</button>
    </div>
  );
}
```

---

### cURL

```bash
# Send a chat message
curl -X POST http://localhost:5000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What does Binjwa IT Solutions do?"}'

# Upload a PDF
curl -X POST http://localhost:5000/upload-pdf \
  -F "files=@/path/to/your/document.pdf"
```

---

## CORS

CORS is enabled for all origins by default (`Flask-CORS`). This means you can call the API from any frontend, on any domain or port, without CORS errors.

If you want to restrict access to specific domains in production, update `app.py`:

```python
CORS(app, origins=["https://your-frontend-domain.com"])
```

---

## Notes for Frontend Developers

- **You do not need to use the built-in UI.** The `GET /` route serves the default HTML UI — you can ignore it entirely and just call `/chat` and `/upload-pdf` from your own application.
- **PDFs are the knowledge base.** The bot only answers questions about what's in the PDF files loaded on the server. Add PDFs to the `./pdfs/` folder on the server, or use the `/upload-pdf` endpoint to upload them at runtime.
- **No authentication** is implemented by default. If you expose this API publicly, consider adding an API key header check or putting it behind a reverse proxy (nginx) with auth.
- **Response time** depends on the AI model. Expect 2–8 seconds per response. Show a loading/typing indicator in your UI while waiting.
- **Chat history** is saved automatically to MongoDB — you do not need to handle persistence on the frontend.
