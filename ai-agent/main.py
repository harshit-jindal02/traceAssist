# ai-agent/main.py

import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import openai

# ─── Environment ────────────────────────────────────────────────────────────────
load_dotenv()  # load .env first
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4")  # default to gpt-4

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set in environment")

openai.api_key = OPENAI_API_KEY

# ─── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("ai-agent")

# ─── App & CORS ────────────────────────────────────────────────────────────────
app = FastAPI(title="TraceAssist AI Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Models ─────────────────────────────────────────────────────────────────────
class SuggestRequest(BaseModel):
    app_id: str

class SuggestResponse(BaseModel):
    suggestions: list[str]
    model_used: str

# ─── Endpoint ──────────────────────────────────────────────────────────────────
@app.post("/suggest", response_model=SuggestResponse)
async def suggest(req: SuggestRequest):
    logger.info(f"Received suggestion request for app_id={req.app_id}")
    prompt = (
        f"You are an observability expert. Provide recommendations for instrumenting "
        f"the application with ID {req.app_id} in Kubernetes using OpenTelemetry & SigNoz."
    )

    try:
        resp = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are an observability expert."},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.3,
            max_tokens=500,
        )
        suggestions = [c.message.content.strip() for c in resp.choices]
        logger.info(f"AI suggestions generated with model={resp.model}")
        return SuggestResponse(suggestions=suggestions, model_used=resp.model)

    except openai.error.RateLimitError as e:
        logger.error(f"Rate limit error: {e}")
        raise HTTPException(status_code=429, detail="OpenAI rate limit exceeded.")
    except openai.error.APIConnectionError as e:
        logger.error(f"API connection error: {e}")
        raise HTTPException(status_code=503, detail="Could not connect to OpenAI API.")
    except openai.error.OpenAIError as e:
        logger.error(f"OpenAI API error: {e}")
        raise HTTPException(status_code=500, detail=f"OpenAI API error: {str(e)}")
    except Exception as e:
        logger.exception("Unexpected error in /suggest")
        raise HTTPException(status_code=500, detail="Internal server error.")
