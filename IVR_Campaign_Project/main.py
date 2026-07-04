from fastapi import FastAPI, Request
import uvicorn

# Import the IVR router which contains the CampaignQueue and all endpoints
from ivr import router as ivr_router

app = FastAPI(title="Binjwa IT Solutions - IVR Campaign Server")

# Include the IVR routes
app.include_router(ivr_router)

@app.get("/")
async def root():
    return {"message": "IVR Campaign Server is running! Please use the /ivr endpoints."}

if __name__ == "__main__":
    print("🚀 Starting IVR Campaign Server on port 8000...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
