import re
import os

filepath = r"c:\Ai voice calling agent\Vobiz_Working_Project\dynamic_ivr.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Inject actionId retrieval right after webhookId retrieval for query_params
content = re.sub(
    r'(webhookId\s*=\s*query_params\.get\("webhookId"(?:,\s*.*?)?\)\n)',
    r'\1    actionId = query_params.get("actionId", data.get("actionId", "") if "data" in locals() else "")\n',
    content
)

content = re.sub(
    r'(webhookId\s*=\s*request\.query_params\.get\("webhookId"(?:,\s*.*?)?\)\n)',
    r'\1    actionId = request.query_params.get("actionId", body.get("actionId", "") if "body" in locals() else data.get("actionId", "") if "data" in locals() else "")\n',
    content
)

# 2. Add "actionId": actionId to push_to_crm calls (that have "event_type")
# Using a regex that looks for event_type inside push_to_crm
def replace_push_to_crm(match):
    inner_text = match.group(1)
    if '"actionId"' not in inner_text:
        return match.group(0).replace('"event_type"', '"actionId": actionId,\n            "event_type"')
    return match.group(0)

content = re.sub(r'(push_to_crm\(\{[\s\S]*?"event_type"[\s\S]*?\}\s*,\s*webhookId\))', replace_push_to_crm, content)

# 3. Add &amp;actionId={actionId} to URLs inside XML tags
content = re.sub(
    r'(&amp;webhookId=\{webhookId\}(?!&amp;actionId))',
    r'\1&amp;actionId={actionId}',
    content
)

# Replace already modified from previous run if any duplicate
content = content.replace('&amp;actionId={actionId}&amp;actionId={actionId}', '&amp;actionId={actionId}')

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Patched dynamic_ivr.py")
