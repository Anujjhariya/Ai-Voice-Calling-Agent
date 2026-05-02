import sqlite3
import json
from datetime import datetime

DB_FILE = "voice_agent.db"

def init_db():
    """Create the calls table if it doesn't exist."""
    try:
        conn = sqlite3.connect(DB_FILE, timeout=20)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_sid TEXT UNIQUE,
                recording_url TEXT,
                transcript TEXT,
                summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Could not initialize DB (it might be locked by DB Browser): {e}")

def save_call_data(call_sid: str, transcript: list, summary: str, recording_url: str = ""):
    """Save the final call data to SQLite."""
    conn = sqlite3.connect(DB_FILE, timeout=20)
    cursor = conn.cursor()
    
    # Store transcript as a JSON string
    transcript_json = json.dumps(transcript, ensure_ascii=False)
    
    cursor.execute('''
        INSERT INTO calls (call_sid, transcript, summary, recording_url)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(call_sid) DO UPDATE SET
            transcript=excluded.transcript,
            summary=excluded.summary,
            recording_url=excluded.recording_url
    ''', (call_sid, transcript_json, summary, recording_url))
    
    conn.commit()
    conn.close()
    print(f"💾 Call {call_sid} saved to database!")

# Initialize DB on load
init_db()
