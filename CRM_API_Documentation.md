# Voice AI & IVR Server - API Documentation

This document outlines the API endpoints available on the Voice Server, allowing the CRM to trigger automated calls (IVR or AI Agent) and retrieve call transcripts, lead tags, and summaries.

---

## 1. Trigger Bulk IVR Campaign
Adds a list of leads to the IVR Campaign Queue. The server will sequentially dial each lead, waiting for the active call to finish before dialing the next to avoid telecom line saturation.

**Endpoint:** `POST /ivr/trigger_campaign`  
**Content-Type:** `application/json`

### Request Body
```json
{
  "leads": [
    {
      "name": "Rahul Sharma",
      "phone": "+918319688692"
    },
    {
      "name": "Vivek Singh",
      "phone": "+918128953806"
    }
  ]
}
```

### Response (200 OK)
```json
{
  "status": "started",
  "queued": 2
}
```

---

## 2. Trigger Single AI Agent Call (Conversational)
This endpoint triggers the ultra-realistic Conversational AI agent (Murf + LLM) for a specific user.

**Endpoint:** `POST /api/trigger_ai_call`  
**Content-Type:** `application/json`

### Request Body
```json
{
  "name": "Anjali",
  "phone": "+916261044560"
}
```

---

## 3. CRM Webhook Receivers (Receiving Data from Voice Server)
To display live tags and summaries inside the CRM dashboard, the CRM Developer must expose a Webhook Endpoint (e.g., `POST https://crm.yourcompany.com/api/webhooks/voice`). 

The Voice Server will push JSON payloads to this URL at different stages of the call.

### A. Lead Tagging Event (Interested vs Not Interested)
When the user presses '1' (Meeting) or '2' (Not Interested) on their keypad, the Voice Server will instantly push this tag to the CRM.

**Payload sent to CRM:**
```json
{
  "event_type": "lead_tag",
  "call_uuid": "b2dd5cc0-d89c-4778-88cb-30f647ca6c51",
  "customer_phone": "+918319688692",
  "customer_name": "Rahul Sharma",
  "tag": "Interested", 
  "key_pressed": "1",
  "timestamp": "2026-05-07T10:15:30Z"
}
```
*(Note: If the user presses 2, the tag will be `"Not Interested"`).*

### B. Live Transcript Event
When the user speaks to the AI (e.g., specifying their meeting time), the transcribed text is sent to the CRM.

**Payload sent to CRM:**
```json
{
  "event_type": "customer_speech",
  "call_uuid": "b2dd5cc0-d89c-4778-88cb-30f647ca6c51",
  "customer_phone": "+918319688692",
  "text": "मुझे कल दोपहर 2 बजे मीटिंग करनी है",
  "timestamp": "2026-05-07T10:15:45Z"
}
```

### C. Final Call Summary & Meeting Status
Triggered when the call physically hangs up. This provides the CRM with the final status of the lead and Google Calendar booking result.

**Payload sent to CRM:**
```json
{
  "event_type": "call_summary",
  "call_uuid": "b2dd5cc0-d89c-4778-88cb-30f647ca6c51",
  "customer_phone": "+918319688692",
  "customer_name": "Rahul Sharma",
  "final_status": "Meeting Booked",
  "meeting_time": "08 May 2026 at 02:00 PM",
  "sms_sent": true,
  "duration_seconds": 45
}
```

---

## 4. CRM Developer Integration Notes
- **Webhooks:** The CRM developer must provide the Webhook URL to the Voice Server administrator. The Python Server will be updated to automatically `requests.post()` the JSON payloads detailed above to the CRM.
- **Queueing:** Do not send 100 simultaneous requests to the single-call endpoint. Always use `/ivr/trigger_campaign` to utilize the Voice Server's smart pacing algorithm, preventing telecom line rejections.
