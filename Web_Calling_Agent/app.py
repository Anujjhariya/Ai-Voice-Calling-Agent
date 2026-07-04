import os
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from web_agent import router as web_agent_router

app = FastAPI(title="Binjwa IT Solutions — Standalone Web Voice Agent")

# Enable CORS for widget embedding
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the web-agent Websocket & Page routes
app.include_router(web_agent_router)

# Mount the static directory for widget.js and web_agent.html
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/demo", response_class=HTMLResponse)
async def demo_page():
    """Demo website showing the embedded voice widget."""
    html_path = os.path.join(os.path.dirname(__file__), "static", "demo.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/")
async def root():
    return {
        "status": "online",
        "message": "Standalone Web Voice Agent is running.",
        "endpoints": {
            "demo": "/demo",
            "standalone_page": "/web-agent/",
            "websocket_endpoint": "/web-agent/ws"
        }
    }

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8001, reload=True)
