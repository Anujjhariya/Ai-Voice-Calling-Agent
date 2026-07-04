# 📞 AI Voice Agent — CRM Integration Guide
**For: CRM Developer**  
**Prepared by: Binjva IT Solutions**  
**Version: 1.0**

---

## Overview

This document explains how the AI Voice Agent communicates with your CRM system. There are **two parts** to this integration:

1. **CRM → AI Server:** Your CRM triggers a phone call by calling our API  
2. **AI Server → CRM:** Our server automatically sends live call events to your webhook endpoint as the call progresses

---

## Part 1: Triggering a Call (CRM → AI Server)

When you want the AI to call a customer, make a `POST` request to our server.

### Endpoint
```
POST https://[AI_SERVER_URL]/ivr/trigger_single_call
Content-Type: application/json
```

### Request Body
```json
{
    "phone": "+918319688692",
    "name": "Vivek"
}
```

### Successful Response
```json
{
    "status": "success",
    "message": "Single call triggered successfully to Vivek"
}
```

> **Note:** Replace `[AI_SERVER_URL]` with the live server address provided by the Binjva IT team.

---

## Part 2: Receiving Live Call Events (AI Server → CRM)

### What You Need to Build

Create **one single endpoint** on your CRM server that accepts `POST` requests.

> **Important:** You need to create a `POST` endpoint (not GET), because our server will be **sending** data to you.

### Your Webhook Endpoint (Example)
```
POST https://crm.yourcompany.com/api/voice-webhook
```

Once built, share this URL with us. We will configure it on our server.

---

### How It Works (Simple Explanation)

```
Our AI Server                        Your CRM Server
      │                                     │
      │  POST /api/voice-webhook            │
      │  { "event_type": "call_initiated" } │
      │ ───────────────────────────────────▶│
      │                                     │ ← You receive this here
      │                                     │ ← Update your database
```

Every time something happens during a call, we automatically send you a `POST` request with a JSON body. You read the `event_type` field to know what happened and update your CRM accordingly.

---

## Complete Call Timeline & Event Payloads

Below is the full sequence of events you will receive, in order:

---

### Event 1: `call_initiated`
**When:** The moment the call is triggered from our system (phone is dialing)

```json
{
    "event_type": "call_initiated",
    "customer_phone": "+918319688692",
    "customer_name": "Vivek",
    "agent_type": "ivr_menu"
}
```

**Your Action:** Mark the lead as `Call Initiated / Dialing` in CRM.

---

### Event 2: `call_picked_up`
**When:** The customer picks up the phone

```json
{
    "event_type": "call_picked_up",
    "call_uuid": "24117a1b-2f92-4339-ba6d",
    "customer_name": "Vivek",
    "agent_type": "ivr_menu"
}
```

**Your Action:** Mark the lead as `Connected / In Call`. Start a call timer if needed.

---

### Event 3: `lead_tag`
**When:** The customer presses a key on their keypad during the IVR menu

```json
{
    "event_type": "lead_tag",
    "call_uuid": "24117a1b-2f92-4339-ba6d",
    "customer_phone": "+918319688692",
    "customer_name": "Vivek",
    "tag": "Interested",
    "key_pressed": "1"
}
```

**Possible `tag` values:**

| `tag` | `key_pressed` | Meaning |
|---|---|---|
| `Interested` | `1` | Customer wants to book a meeting |
| `Not Interested` | `2` | Customer does not want to proceed |
| `Interested in Meeting` | `1` | Customer interested after service info |
| `Needs More Info` | `2` | Customer wants more details |

**Your Action:** Update the lead's status/tag in your CRM.

---

### Event 4: `meeting_booked`
**When:** The AI successfully books a meeting on Google Calendar after the customer confirms a date and time

```json
{
    "event_type": "meeting_booked",
    "call_uuid": "24117a1b-2f92-4339-ba6d",
    "customer_name": "Vivek",
    "meeting_time": "2026-05-10 14:00",
    "agent_type": "ivr_menu"
}
```

**Your Action:** Create a meeting/appointment record in CRM. Set lead status to `Meeting Scheduled`.

---

### Event 5: `call_disconnected`
**When:** The call ends for any reason (customer hung up, call completed, or call was not picked up)

```json
{
    "event_type": "call_disconnected",
    "call_uuid": "24117a1b-2f92-4339-ba6d",
    "agent_type": "ivr_menu"
}
```

**Your Action:** Mark the call as `Completed` in CRM. Stop the call timer.

---

## Detecting a Missed Call

We do not send a separate `missed_call` event. Use this logic:

> If you receive `call_initiated` but do **not** receive `call_picked_up` within **60 seconds**, the customer did not answer → mark as `Missed Call`.

---

## Complete Visual Timeline

```
CUSTOMER PHONE                  OUR AI SERVER              YOUR CRM
      │                               │                        │
      │                               │◀── POST /trigger ──────│
      │◀──── 📲 Ringing ──────────────│ push: call_initiated ──▶│
      │                               │                        │
      │──── ✅ Picks up ─────────────▶│                        │
      │                               │ push: call_picked_up ──▶│
      │◀─── 🔊 Greeting plays ────────│                        │
      │                               │                        │
      │──── ⌨️ Presses 1 ────────────▶│                        │
      │                               │ push: lead_tag ────────▶│
      │◀─── 🔊 Asks meeting time ─────│                        │
      │                               │                        │
      │──── 🗣️ Says "Kal 2 baje" ────▶│                        │
      │                               │ push: meeting_booked ──▶│
      │◀─── 🔊 Confirms booking ──────│                        │
      │                               │                        │
      │──── 📴 Call ends ────────────▶│                        │
      │                               │ push: call_disconnected ▶│
```

---

## Sample Code (How to Receive Events)

### Python (FastAPI)
```python
from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/api/voice-webhook")
async def receive_voice_event(request: Request):
    data = await request.json()
    event = data.get("event_type")

    if event == "call_initiated":
        # Mark lead as dialing
        pass

    elif event == "call_picked_up":
        # Mark lead as connected
        pass

    elif event == "lead_tag":
        tag = data.get("tag")
        phone = data.get("customer_phone")
        # Update lead status with tag
        pass

    elif event == "meeting_booked":
        meeting_time = data.get("meeting_time")
        name = data.get("customer_name")
        # Create appointment in CRM
        pass

    elif event == "call_disconnected":
        call_uuid = data.get("call_uuid")
        # Mark call as completed
        pass

    return {"status": "received"}
```

### Node.js (Express)
```javascript
app.post('/api/voice-webhook', (req, res) => {
    const { event_type, customer_phone, customer_name, tag, meeting_time } = req.body;

    switch (event_type) {
        case 'call_initiated':
            // Mark lead as dialing
            break;
        case 'call_picked_up':
            // Mark lead as connected
            break;
        case 'lead_tag':
            // Update lead status: tag = "Interested" or "Not Interested"
            break;
        case 'meeting_booked':
            // Create appointment: meeting_time = "2026-05-10 14:00"
            break;
        case 'call_disconnected':
            // Mark call as completed
            break;
    }

    res.json({ status: 'received' });
});
```

---

## Setup Checklist for CRM Developer

- [ ] Build a `POST` endpoint on your server (e.g., `/api/voice-webhook`)
- [ ] The endpoint must return `HTTP 200` with any JSON response (e.g., `{"status": "received"}`)
- [ ] Share the full URL with us (e.g., `https://crm.yourcompany.com/api/voice-webhook`)
- [ ] We will configure it on our server — no further action needed from your side
- [ ] Test by triggering a sample call and checking if events arrive at your endpoint

---

## Contact

For any questions about this integration, contact the Binjva IT Solutions development team.
