# 📋 Webhook Payload Reference — All Events
**For: CRM Developer**  
**Server sends these via:** `POST` to your webhook URL  
**Content-Type:** `application/json`

---

## Event 1: `call_initiated`
**Triggered when:** Our server dials the customer's phone (before they pick up)

```json
{
    "event_type": "call_initiated",
    "customer_phone": "918319688692",
    "customer_name": "Anuj",
    "agent_type": "ivr_menu"
}
```

---

## Event 2: `call_picked_up`
**Triggered when:** Customer picks up and the IVR greeting starts playing

```json
{
    "event_type": "call_picked_up",
    "customer_name": "Anuj",
    "agent_type": "ivr_menu"
}
```

---

## Event 3: `lead_tag` — Customer pressed **1** (Interested)
**Triggered when:** Customer presses 1 on their keypad during the main menu

```json
{
    "event_type": "lead_tag",
    "call_uuid": "b2dfa185-190c-42d1-8faa-befc7d935cca",
    "customer_phone": "918319688692",
    "customer_name": "Anuj",
    "tag": "Interested",
    "key_pressed": "1"
}
```

---

## Event 4: `lead_tag` — Customer pressed **2** (Not Interested)
**Triggered when:** Customer presses 2 on their keypad during the main menu

```json
{
    "event_type": "lead_tag",
    "call_uuid": "b2dfa185-190c-42d1-8faa-befc7d935cca",
    "customer_phone": "918319688692",
    "customer_name": "Anuj",
    "tag": "Not Interested",
    "key_pressed": "2"
}
```

---

## Event 5: `lead_tag` — Customer pressed **1** in sub-menu (Interested in Meeting)
**Triggered when:** Customer selects "Book Meeting" from a service sub-menu

```json
{
    "event_type": "lead_tag",
    "call_uuid": "b2dfa185-190c-42d1-8faa-befc7d935cca",
    "customer_phone": "918319688692",
    "customer_name": "Customer",
    "tag": "Interested in Meeting",
    "key_pressed": "1"
}
```

---

## Event 6: `lead_tag` — Customer pressed **2** in sub-menu (Needs More Info)
**Triggered when:** Customer selects "More Information" from a service sub-menu

```json
{
    "event_type": "lead_tag",
    "call_uuid": "b2dfa185-190c-42d1-8faa-befc7d935cca",
    "customer_phone": "918319688692",
    "customer_name": "Customer",
    "tag": "Needs More Info",
    "key_pressed": "2"
}
```

---

## Event 7: `call_summary`
**Triggered when:** Meeting is successfully booked on Google Calendar

```json
{
    "event_type": "call_summary",
    "call_uuid": "b2dfa185-190c-42d1-8faa-befc7d935cca",
    "customer_phone": "+918319688692",
    "customer_name": "Anuj",
    "final_status": "Meeting Booked",
    "meeting_time": "10 May 2026 at 07:00 PM"
}
```

---

## Event 8: `call_disconnected`
**Triggered when:** Call ends for any reason (completed, customer hung up, unanswered)

```json
{
    "event_type": "call_disconnected",
    "agent_type": "ivr_menu"
}
```

---

## All Possible `event_type` Values (Summary)

| `event_type` | When it fires |
|---|---|
| `call_initiated` | When the call is dialed |
| `call_picked_up` | When customer answers |
| `lead_tag` | When customer presses any key |
| `call_summary` | When meeting is booked on calendar |
| `call_disconnected` | When the call ends |

---

## All Possible `tag` Values (inside `lead_tag` event)

| `tag` | `key_pressed` | Meaning |
|---|---|---|
| `Interested` | `1` | Main menu → wants to book meeting |
| `Not Interested` | `2` | Main menu → not interested |
| `Interested in Meeting` | `1` | Service sub-menu → wants to book |
| `Needs More Info` | `2` | Service sub-menu → wants more details |

---

## Complete Handler (Node.js / Express)

Copy this exactly. Handle all 5 event types — your server was returning `HTTP 500` for `call_initiated`, `call_picked_up`, and `call_disconnected` because those cases were missing.

```javascript
const express = require('express');
const app = express();
app.use(express.json());

app.post('/api/agent/voice/:tenantId', (req, res) => {
    const { tenantId } = req.params;
    const data = req.body;
    const event = data.event_type;

    console.log(`[${tenantId}] Received event: ${event}`, data);

    switch (event) {

        case 'call_initiated':
            // Call is dialing — mark lead as "Dialing" in CRM
            // data.customer_phone, data.customer_name, data.agent_type
            console.log(`Call started to ${data.customer_name} (${data.customer_phone})`);
            break;

        case 'call_picked_up':
            // Customer answered — mark lead as "In Call"
            // data.customer_name, data.agent_type
            console.log(`${data.customer_name} picked up the call`);
            break;

        case 'lead_tag':
            // Customer pressed a key — update lead status/tag
            // data.call_uuid, data.customer_phone, data.customer_name, data.tag, data.key_pressed
            console.log(`Lead tagged as: ${data.tag} (pressed ${data.key_pressed})`);
            break;

        case 'call_summary':
            // Meeting booked — create appointment in CRM
            // data.call_uuid, data.customer_phone, data.customer_name, data.final_status, data.meeting_time
            console.log(`Meeting booked for ${data.customer_name} at ${data.meeting_time}`);
            break;

        case 'call_disconnected':
            // Call ended — mark as "Completed"
            // data.agent_type
            console.log(`Call ended`);
            break;

        default:
            // Unknown event — log it but still return 200
            console.log(`Unknown event_type received: ${event}`);
            break;
    }

    // IMPORTANT: Always return HTTP 200, even if you don't handle the event
    res.status(200).json({ status: 'received', event });
});

app.listen(3000, () => console.log('Webhook server running on port 3000'));
```

---

## ⚠️ Important Rule

**Always return `HTTP 200`**, even for unknown events. If your server returns `HTTP 500`, it means your code crashed while processing the event. The `default` case in the switch statement prevents this.

---

## Why You Were Getting HTTP 500

Your server crashed on `call_initiated`, `call_picked_up`, and `call_disconnected` because those `case` blocks were missing in your switch statement. The `default` block was also missing, so any unknown event type caused an unhandled error → `HTTP 500`.
