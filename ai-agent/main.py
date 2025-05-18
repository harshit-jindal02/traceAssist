# 📁 ai_agent/main.py

from fastapi import FastAPI, Request
from pydantic import BaseModel
from openai import OpenAI
import os
import logging

app = FastAPI()

# Load OpenAI API key from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-agent")

class CodeContext(BaseModel):
    language: str
    code_snippet: str
    framework: str | None = None

@app.post("/suggest")
async def suggest_instrumentation(context: CodeContext):
    logger.info("Received code for AI instrumentation suggestion.")

    prompt = f"""
You are an expert software observability engineer. Given the following {context.language} code snippet,
suggest improvements to add observability using OpenTelemetry. 
Highlight relevant code areas and explain briefly why each change is needed. If no improvement is needed, say so.

---
CODE:
{context.code_snippet}
---

Respond with a JSON object like:
{{
  "suggestions": [
    {{ "line": X, "change": "<code change>", "reason": "<why>" }},
    ...
  ]
}}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful AI for suggesting code instrumentation."},
                {"role": "user", "content": prompt},
            ]
        )

        ai_output = response.choices[0].message.content
        logger.info("AI suggestions returned successfully.")
        return {"ai_suggestions": ai_output}

    except Exception as e:
        logger.error(f"Error during AI instrumentation suggestion: {e}")
        return {"error": "AI suggestion failed. Please try again."}


# Run with: uvicorn main:app --host 0.0.0.0 --port 8200
