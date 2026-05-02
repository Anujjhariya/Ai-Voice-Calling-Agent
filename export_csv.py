import sqlite3
import csv
import json

def export_to_csv():
    conn = sqlite3.connect("voice_agent.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    rows = cursor.execute("SELECT * FROM calls ORDER BY id DESC").fetchall()
    
    with open("calls_data.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Date", "Phone Number/SID", "Summary", "Transcript", "Recording URL"])
        
        for row in rows:
            # Format transcript to be readable in Excel
            try:
                transcript_data = json.loads(row['transcript'])
                transcript_text = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in transcript_data])
            except:
                transcript_text = row['transcript']
                
            writer.writerow([
                row['id'], 
                row['created_at'], 
                row['call_sid'], 
                row['summary'], 
                transcript_text,
                row['recording_url']
            ])
            
    conn.close()
    print("✅ डेटाबेस 'calls_data.csv' फाइल में Export हो गया है! अब आप इसे Excel में खोल सकते हैं।")

if __name__ == "__main__":
    export_to_csv()
