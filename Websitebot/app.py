import os
import re
import random
from datetime import datetime
from collections import Counter
from difflib import get_close_matches
from typing import List

import fitz  # PyMuPDF
import httpx
import uvicorn
from pymongo import MongoClient
from dotenv import load_dotenv

from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

# Import our voice agent router
from web_agent import router as web_agent_router

load_dotenv()

app = FastAPI(title="Binjwa IT Solutions — Unified Chat & Voice Assistant")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the web-agent Websocket & Standalone UI routes
app.include_router(web_agent_router)

# Mount static files for JavaScript widget, css etc.
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates setup
templates = Jinja2Templates(directory="templates")

# MongoDB
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI)
db = client["pdf_chatbot"]
chat_collection = db["chat_history"]

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# Global variables
pdf_pages = []
PDF_FOLDER = "./pdfs"
domain_topic = "General Business"
domain_keywords = []

models = [
    "anthropic/claude-3-haiku",
    "google/gemini-1.5-flash",
    "meta-llama/llama-3.1-8b-instruct",
    "mistralai/mistral-7b-instruct-v0.1"
]

predefined_answers = {
    "hi": "Hello 👋 How can I help you?",
    "hello": "Hello 👋 How can I help you?",
    "hey": "Hey 👋 How can I assist you?",
    "hy": "Hey 👋 How can I assist you?",
    "hii": "Hello 👋 How can I help you?",
    "who are you": "I am your AI assistant.",
    "help": "You ask Me \n 1. what is binjwa IT slution \n 2. what service they provide \n Like that... ",
    "thanks": "You're welcome 😊",
    "thank you": "You're welcome 😊",
    "thank": "You're welcome 😊",
    "bye": "Goodbye 👋"
}

fallback_answers = [
    "I couldn’t find this information in our scope.",
    "This question is outside the current knowledge base.",
    "No relevant data found in uploaded content.",
    "I don’t have enough context for this query."
]

def ask_ai(messages, max_tokens=250, temperature=0.1):
    for model in models:
        try:
            res = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                },
                timeout=30.0
            )

            if res.status_code == 200:
                data = res.json()
                if "choices" in data and len(data["choices"]) > 0:
                    return data["choices"][0]["message"]["content"]
            else:
                print(f"Error {res.status_code} from {model}: {res.text}")
        except Exception as e:
            print(f"Exception calling {model}: {e}")
            continue

    return "NOT_FOUND"

def analyze_pdf_domain():
    global domain_topic, domain_keywords
    if not pdf_pages:
        return
       
    stopwords = set(["the", "and", "is", "in", "it", "to", "of", "for", "on", "with", "as", "this", "that", "are", "by", "an", "be", "or", "from", "at", "which", "not", "we", "can", "our", "you", "your", "a", "will", "all", "has", "have", "been", "their", "they"])
   
    word_counts = Counter()
    sample_text = ""
    for p in pdf_pages:
        text = p["text"]
        if len(sample_text) < 10000:
            sample_text += text + "\n"
        words = re.findall(r"[a-z]{3,}", text)
        word_counts.update(w for w in words if w not in stopwords)
       
    domain_keywords = [w[0] for w in word_counts.most_common(30)]
   
    messages = [
        {"role": "system", "content": "You are a text analyst. Analyze the following document sample and output a single short sentence describing its main domain/topic/business. Return ONLY the sentence."},
        {"role": "user", "content": sample_text[:8000]}
    ]
    response = ask_ai(messages, max_tokens=50)
    if response and "NOT_FOUND" not in response:
        domain_topic = response.strip()
    else:
       domain_topic = "Specific Business/Domain handled by this assistant"

def load_pdfs_from_folder():
    global pdf_pages
    pages = []
 
    if not os.path.exists(PDF_FOLDER):
        return
 
    for file in os.listdir(PDF_FOLDER):
        if file.lower().endswith(".pdf"):
            path = os.path.join(PDF_FOLDER, file)
            try:
                pdf = fitz.open(path)
                for i, page in enumerate(pdf):
                    text = page.get_text()
                    if text.strip():
                        pages.append({
                            "page": i + 1,
                            "file": file,
                            "text": text.lower()
                        })
            except Exception as e:
                print(f"Error reading {file}: {e}")
 
    pdf_pages = pages
    analyze_pdf_domain()

def clean_response(text):
    text = re.sub(r"\*", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def build_vocab(pdf_pages):
    vocab = set()
    for p in pdf_pages:
        words = re.findall(r"[a-zA-Z]+", p["text"].lower())
        vocab.update(words)
    return list(vocab)

def fix_words(words, vocab):
    fixed = []
    for w in words:
        w = w.strip().lower()
        if not w:
            continue
        if w in vocab:
            fixed.append(w)
            continue
        match = get_close_matches(w, vocab, n=1, cutoff=0.6)
        if match:
            fixed.append(match[0])
        else:
            fixed.append(w)
    return fixed

def score_page(page_text, query_words, user_msg_lower):
    score = 0
    if len(user_msg_lower) > 4 and user_msg_lower in page_text:
        score += 10
    for w in query_words:
        if w in page_text:
            score += 1
            score += page_text.count(w) * 0.1
    return score

# ================= APP LIFESPAN / STARTUP =================
@app.on_event("startup")
async def startup_event():
    load_pdfs_from_folder()

# ================= WEB UI ROUTE =================
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")

# ================= CHATBOT API ROUTES =================
@app.post("/upload-pdf")
async def upload_pdf(files: List[UploadFile] = File(...)):
    if not files or all(f.filename == "" for f in files):
        return JSONResponse({"success": False, "error": "No files selected"}, status_code=400)

    if not os.path.exists(PDF_FOLDER):
        os.makedirs(PDF_FOLDER)

    for file in files:
        if file.filename and file.filename.endswith(".pdf"):
            path = os.path.join(PDF_FOLDER, file.filename)
            with open(path, "wb") as buffer:
                buffer.write(await file.read())

    # Reload all PDFs
    load_pdfs_from_folder()

    return JSONResponse({
        "success": True,
        "message": "PDFs uploaded and processed successfully!"
    })

@app.post("/chat")
async def chat(request: Request):
    global pdf_pages, domain_topic, domain_keywords
    
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    user_message = data.get("message", "").strip()
    if not user_message:
        return JSONResponse({"error": "Message required"}, status_code=400)

    # ---------- STATIC ----------
    if user_message.lower() in predefined_answers:
        return JSONResponse({
            "success": True,
            "response": predefined_answers[user_message.lower()]
        })

    if not pdf_pages:
        return JSONResponse({
            "success": True,
            "response": random.choice(fallback_answers)
        })

    # ---------- VOCAB ----------
    vocab = build_vocab(pdf_pages)

    # ---------- CLEAN QUERY ----------
    stopwords = set(["what", "is", "the", "and", "in", "to", "of", "for", "on", "with", "as", "this", "that", "are", "by", "an", "be", "or", "from", "at", "which", "not", "we", "can", "our", "you", "your", "how", "why", "when", "where", "who", "do", "does", "did", "a", "it", "they", "them", "their", "has", "have", "had", "been", "will", "would", "should", "could", "about", "like", "tell", "me", "kya", "ky", "hai", "h", "ka", "ki", "ke", "ko", "me", "se", "batao", "kaise", "kon", "kaha", "karo", "karna", "chahiye", "diya", "mera", "meri", "hum", "tum", "aap", "uska", "uski", "unka", "unki", "hain", "tha", "thi", "the", "hu", "hoon", "nahi", "nhi"])
    words = re.findall(r"[a-zA-Z]+", user_message.lower())
    filtered_words = [w for w in words if w not in stopwords]
    if not filtered_words:
        filtered_words = words
    query_words = fix_words(filtered_words, vocab)

    # ---------- IMPROVED SCORING ----------
    ranked_pages = []
    user_msg_lower = user_message.lower()

    for p in pdf_pages:
        score = score_page(p["text"], query_words, user_msg_lower)
        if score > 0:
            ranked_pages.append((score, p))

    ranked_pages.sort(reverse=True, key=lambda x: x[0])

    top_pages = ranked_pages[:5]
    top_context = ""
    for score, p in top_pages:
        top_context += f"--- Page {p['page']} from {p['file']} ---\n{p['text']}\n\n"

    top_context = top_context[:12000]

    # ---------- DETECT LANGUAGE ----------
    hinglish_keywords = {"kya", "ky", "hai", "h", "ka", "ki", "ke", "ko", "me", "se", "batao", "kaise", "kon", "kaha", "karo", "karna", "chahiye", "diya", "mera", "meri", "hum", "tum", "aap", "uska", "uski", "unka", "unki", "hain", "tha", "thi", "the", "hu", "hoon", "nahi", "nhi"}
    user_words = set(re.findall(r"[a-zA-Z]+", user_message.lower()))
    is_hinglish = bool(user_words.intersection(hinglish_keywords))
    detected_language = "Hinglish (Hindi written in English alphabet)" if is_hinglish else "English"

    bot_response = "NOT_FOUND"

    # ---------- 1. PDF FIRST POLICY ----------
    context_str = top_context if top_context.strip() else "No specific document context available. Rely on general knowledge about Binjwa IT Solutions."
    pdf_first_prompt = f"""
You are a helpful assistant for Binjwa IT Solutions.
RULES:
1. Answer the user's question using the provided CONTEXT.
2. If the user asks about a term or topic mentioned in the CONTEXT (like CRM, Binjwa IT Solutions, services, etc.), provide a helpful answer. You may use your general knowledge to supplement the answer if the context doesn't have a full definition.
3. If the user asks directly about "Binjwa", "Binjwa IT Solutions", "who are you", or what the company does, you MUST provide a helpful introduction about the company, using the context if available, or your general knowledge. DO NOT reply NOT_FOUND for questions about the company itself.
4. If the user's question is COMPLETELY UNRELATED to the business, services, or the provided CONTEXT (e.g., general programming questions, weather, politics), you MUST reply EXACTLY with the word: NOT_FOUND
5. Keep the answer short (2-3 bullet points or a brief paragraph).
6. Do NOT mention "the document" or "the context" in your response.

LANGUAGE RULES (CRITICAL):
Based on the user's query, you MUST reply in {detected_language}.
If the required language is Hinglish, write the response in conversational Hindi using the English alphabet. Example: "Binjwa IT solution ek software company hai..."
If the required language is English, write the response in English.
IMPORTANT: Do NOT prefix your response with labels like "Hinglish response:" or "English response:". Start directly with the text of your answer.

CONTEXT:
{context_str}
"""
    messages = [
        {"role": "system", "content": pdf_first_prompt},
        {"role": "user", "content": user_message}
    ]
    response = ask_ai(messages, max_tokens=300)
    
    if response and "NOT_FOUND" not in response:
        bot_response = response

    # ---------- 2. NO FALLBACK (STRICT PDF) ----------
    if bot_response == "NOT_FOUND" or "NOT_FOUND" in bot_response:
        bot_response = "This question is outside our knowledge scope."
    else:
        bot_response = re.sub(r"^(Hinglish\s*response|English\s*response|Response)\s*:\s*", "", bot_response, flags=re.IGNORECASE).strip()

    bot_response = clean_response(bot_response)

    chat_collection.insert_one({
        "question": user_message,
        "answer": bot_response,
        "created_at": datetime.utcnow()
    })

    return JSONResponse({
        "success": True,
        "response": bot_response
    })

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=True)