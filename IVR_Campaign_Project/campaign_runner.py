import os
import time
import json
import PyPDF2
from groq import Groq
from dotenv import load_dotenv
from outbound_vobiz_ivr import make_vobiz_ivr_call

load_dotenv()

def extract_text_from_pdf(pdf_path: str) -> str:
    """Read all text from a PDF file."""
    text = ""
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"Error reading PDF: {e}")
    return text

def parse_leads_from_text(text: str) -> list:
    """Use Groq to extract names and phone numbers from messy text."""
    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    
    prompt = (
        "I have extracted the following text from a PDF file containing a list of leads. "
        "Please find all the people mentioned and their phone numbers. "
        "Return the result ONLY as a valid JSON array of objects, where each object has 'name' and 'phone' keys. "
        "Example format: [{\"name\": \"Rahul\", \"phone\": \"+918319688692\"}]. "
        "Make sure the phone numbers are formatted nicely, preferably starting with +91 if they are Indian numbers. "
        "Do NOT include any markdown formatting, backticks, or other text. ONLY return the JSON array.\n\n"
        f"TEXT:\n{text[:6000]}" # Limiting text to avoid token limits for this example
    )
    
    print("Parsing PDF text with Groq AI to find names and numbers...")
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        result_content = response.choices[0].message.content.strip()
        
        # Clean up in case Groq returns markdown
        if result_content.startswith("```json"):
            result_content = result_content[7:]
        if result_content.endswith("```"):
            result_content = result_content[:-3]
            
        leads = json.loads(result_content.strip())
        return leads
    except Exception as e:
        print(f"Error parsing leads: {e}")
        return []

def run_campaign(pdf_path: str):
    if not os.path.exists(pdf_path):
        print(f"Could not find PDF file: {pdf_path}")
        return
        
    print(f"Reading {pdf_path}...")
    raw_text = extract_text_from_pdf(pdf_path)
    
    if not raw_text.strip():
        print("No text could be extracted from the PDF.")
        return
        
    leads = parse_leads_from_text(raw_text)
    
    if not leads:
        print("No leads were found in the PDF.")
        return
        
    print(f"\nFound {len(leads)} leads! Starting campaign...\n")
    
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:8000")
    if "ngrok" not in base_url and "127.0.0.1" in base_url:
        print("Note: BASE_URL in .env seems to be missing or local. Using local server for queuing.")
        
    try:
        import requests
        print(f"Sending {len(leads)} leads to the server queue...")
        response = requests.post(f"{base_url}/ivr/trigger_campaign", json={"leads": leads})
        
        if response.status_code == 200:
            print(f"\\n✅ Successfully queued! The server will now dial them sequentially, waiting for one call to finish before starting the next.")
        else:
            print(f"❌ Failed to queue: {response.text}")
    except Exception as e:
        print(f"❌ Error talking to server: {e}")

if __name__ == "__main__":
    # Put the name of your PDF file here
    PDF_FILE = "Name.pdf" 
    run_campaign(PDF_FILE)
