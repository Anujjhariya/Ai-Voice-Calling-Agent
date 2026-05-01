import os
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
TOKEN_FILE = "token.json"

def get_calendar_service():
    """Authenticate and return a Google Calendar service object."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)


def book_meeting(name: str, dt_str: str) -> str:
    """
    Book a 30-minute meeting on Google Calendar.
    - name: customer's name
    - dt_str: datetime string in format "YYYY-MM-DD HH:MM"
    Returns a confirmation message string.
    """
    try:
        service = get_calendar_service()
        start_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(minutes=30)

        event = {
            "summary": f"Meeting with {name}",
            "description": "Booked via AI Voice Agent",
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": "Asia/Kolkata"
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": "Asia/Kolkata"
            },
        }

        service.events().insert(calendarId="primary", body=event).execute()
        formatted = start_dt.strftime("%d %B %Y at %I:%M %p")
        return f"Meeting successfully booked for {name} on {formatted} IST."

    except Exception as e:
        return f"Sorry, I could not book the meeting. Error: {str(e)}"


if __name__ == "__main__":
    # Run this once to authorize Google Calendar access
    print("Authorizing Google Calendar...")
    get_calendar_service()
    print("Authorization successful! token.json created.")
