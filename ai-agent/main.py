# ai-agent/main.py

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import openai
import os

openai.api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI()

# ─── CORS ───────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ────────────────────────────────────────────────────────────────────────────────

class SuggestRequest(BaseModel):
    app_id: str
    # add other fields (code snippet, files) as needed

@app.post("/suggest")
async def suggest(req: SuggestRequest):
    try:
        completion = openai.ChatCompletion.create(
            model="gpt-4", 
            messages=[{"role":"system","content":"You are an observability expert."},
                      {"role":"user","content":f"Instrument code improvements for app {req.app_id}"}]
        )
        suggestions = [choice.message.content for choice in completion.choices]
        return {"suggestions": suggestions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
