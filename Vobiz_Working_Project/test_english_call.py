import requests

# Make sure this matches the port your local server is running on (usually 8000)
url = "http://127.0.0.1:8000/ivr/trigger_single_call" 

payload = {
    "phone": "918319688692", # e.g. "919876543210"
    "name": "Anuj",
    "webhookId": "test-english-webhook-12345", # The one from your logs
    "lang": "en"  # <--- THIS triggers the English flow
}

response = requests.post(url, json=payload)
print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")