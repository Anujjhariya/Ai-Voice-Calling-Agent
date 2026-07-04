# AI PDF Chatbot

A powerful, context-aware AI chatbot built with Flask that can answer questions based on your PDF documents. It integrates with OpenRouter to leverage top-tier Large Language Models (LLMs) and uses MongoDB to persist chat history.

## Features

- ** Document Context:** Upload multiple PDFs. The bot reads, extracts, and uses the content to answer your domain-specific questions.
- ** Multi-Model AI:** Uses OpenRouter API to route requests to powerful models like Claude 3 Haiku, Gemini 1.5 Flash, Llama 3.1, and Mistral.
- ** Multilingual (Hinglish/English):** Automatically detects if you are asking questions in English or Hinglish (Hindi in English script) and responds in the exact same tone and language.
- ** Chat History:** Automatically saves all user questions and bot responses to a local MongoDB database.
- ** Modern UI:** A beautiful, responsive frontend interface with dynamic backgrounds, chat bubbles, and file upload capabilities.
- ** Fallback Mechanism:** Includes predefined answers for greetings and intelligent fallback responses when a query is out-of-scope.

## Prerequisites

Before running the project, ensure you have the following installed:
- [Python 3.8+](https://www.python.org/downloads/)
- [MongoDB](https://www.mongodb.com/try/download/community) (Running locally on default port `27017`)
- An API Key from [OpenRouter](https://openrouter.ai/)

## Installation

1. **Clone or Download the Repository**
   Navigate to the project directory:
   ```bash
   cd "webside bot"
   ```

2. **Set Up the Configuration File**
   Create a file named `config.py` in the root directory and add your OpenRouter API key:
   ```python
   # config.py
   OPENROUTER_API_KEY = "your_openrouter_api_key_here"
   ```

3. **Install Dependencies**
   Install the required Python libraries using the provided `requirements.txt`:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. **Start MongoDB**
   Ensure your local MongoDB server is running.
   
2. **Add Initial PDFs (Optional)**
   You can place default PDF files inside a folder named `pdfs` in the root directory. The application will load these automatically when the server starts.

3. **Run the Server**
   Start the Flask application:
   ```bash
   python app.py
   ```

4. **Access the Web Interface**
   Open your browser and navigate to:
   ```
   http://127.0.0.1:5000/
   ```
   From here, you can upload more PDFs and start chatting!

## Project Structure

```text
├── app.py               # Main Flask backend application
├── config.py            # API Keys configuration (Not included, must be created)
├── requirements.txt     # Python dependencies
├── templates/
│   └── index.html       # Chatbot Frontend Interface
└── pdfs/                # Directory where uploaded PDFs are stored
```

## How It Works

1. **PDF Processing:** `PyMuPDF (fitz)` extracts text from documents. A custom vocabulary and frequency counter analyzes the primary domain.
2. **Search & Scoring:** When a user asks a question, the backend removes stopwords, fixes spellings via fuzzy matching, and scores pages to find the most relevant context.
3. **AI Generation:** The retrieved context + the user's question are sent to the LLM with strict prompts dictating the response language (English/Hinglish) and boundaries (preventing out-of-scope answers).
4. **Database Logging:** The interaction is stored via `pymongo` for auditing and history tracking.
