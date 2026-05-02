import sqlite3
import json

def check_latest_call():
    try:
        conn = sqlite3.connect("voice_agent.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        row = cursor.execute("SELECT * FROM calls ORDER BY id DESC LIMIT 1").fetchone()
        
        if row:
            print("="*50)
            print("[LATEST CALL RECORD FOUND IN DATABASE]")
            print("="*50)
            print(f"ID:            {row['id']}")
            print(f"Call SID:      {row['call_sid']}")
            print(f"Time:          {row['created_at']}")
            print(f"Recording URL: {row['recording_url']}")
            print("-" * 50)
            print("[SUMMARY]")
            print(row['summary'])
            print("-" * 50)
            print("[TRANSCRIPT]")
            
            transcript = json.loads(row['transcript'])
            for msg in transcript:
                role = "Customer" if msg["role"] == "user" else "Agent"
                print(f"{role}: {msg['content']}")
            
            print("="*50)
        else:
            print("No calls found in the database yet. Make sure the call ended completely!")
            
        conn.close()
    except Exception as e:
        print(f"Error reading database: {e}")

if __name__ == "__main__":
    check_latest_call()
