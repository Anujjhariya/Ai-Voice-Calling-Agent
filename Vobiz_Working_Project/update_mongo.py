import sys
from pymongo import MongoClient

webhookId = "fbd11ad8-c85e-481e-a6ea-5b4363577700"
client = MongoClient('mongodb://localhost:27017')
col = client['Binjwa_IT_Solutions']['IVR_Flows']

doc = col.find_one({"webhookId": webhookId})
if not doc:
    print("Flow not found in DB!")
    sys.exit(1)

flow = doc.get("flow_json", {})
nodes = flow.get("nodes", {})

# Modify the greeting node to forward to HR on 1
if "node_greeting" in nodes:
    nodes["node_greeting"]["branches"]["1"] = "node_forward_hr"

# Add the HR forwarding node
nodes["node_forward_hr"] = {
    "type": "action_forward",
    "text": "ठीक है, हम आपकी कॉल हमारे HR department को transfer कर रहे हैं। कृपया लाइन पर बने रहें।",
    "forward_number": "+918827614849",  # Placeholder, tell user to update
    "end_call": True
}

col.update_one({"webhookId": webhookId}, {"$set": {"flow_json": flow}})
print("Successfully updated flow in MongoDB!")
