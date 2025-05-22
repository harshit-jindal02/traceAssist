import os
import shutil
import zipfile
import uuid
import logging

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import Optional, Any

from git import Repo, GitCommandError
from dotenv import load_dotenv
from openai import OpenAI, APIConnectionError, RateLimitError, APIStatusError

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize OpenAI client
if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY environment variable not set. AI features will not work.")
    openai_client = None
else:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Base directory for user-uploaded applications
BASE_DIR = "user-apps"
os.makedirs(BASE_DIR, exist_ok=True)

# --- Pydantic Models ---
class GitCloneRequest(BaseModel):
    repo_url: str
    branch: Optional[str] = Field(default="main")

    @validator("branch", pre=True, always=True)
    def normalize_default_branch(cls, v: Any) -> str:
        if v is None:
            return "main"
        if v == "master":
            return "main"
        if isinstance(v, str):
            return v
        raise TypeError(f"Branch must be a string; got {type(v).__name__}")

class GitCloneResponse(BaseModel):
    app_id: str
    cloned_branch: Optional[str]

class AISuggestionResponse(BaseModel):
    app_id: str
    suggestions: str
    model_used: Optional[str] = None

# --- Helper Functions ---
def detect_language(app_path: str) -> str:
    py_count = 0
    java_count = 0
    has_package_json = False

    for root, dirs, files in os.walk(app_path):
        dirs[:] = [d for d in dirs if d not in ['.git', 'node_modules', '__pycache__', 'venv']]
        if 'package.json' in files:
            has_package_json = True
        for f in files:
            if f.endswith('.py'):
                py_count += 1
            if f.endswith('.java'):
                java_count += 1

    if has_package_json:
        return 'node'
    if py_count > 0 and java_count == 0:
        return 'python'
    if java_count > 0:
        return 'java'
    return 'unknown'

# (Include get_project_context_for_ai as before; omitted here for brevity)

# --- Endpoints ---
@app.post("/upload")
async def upload_zip(file: UploadFile = File(...)):
    app_id = str(uuid.uuid4())
    app_dir = os.path.join(BASE_DIR, app_id)
    os.makedirs(app_dir, exist_ok=True)

    try:
        zip_path = os.path.join(app_dir, "app.zip")
        with open(zip_path, 'wb') as buffer:
            shutil.copyfileobj(file.file, buffer)
        with zipfile.ZipFile(zip_path, 'r') as z_ref:
            z_ref.extractall(app_dir)
        os.remove(zip_path)
    except Exception as e:
        logger.error(f"Error processing upload for {app_id}: {e}")
        if os.path.isdir(app_dir):
            shutil.rmtree(app_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))

    return {"app_id": app_id}

@app.post("/clone")
async def clone_repo(req: GitCloneRequest) -> GitCloneResponse:
    app_id = str(uuid.uuid4())
    app_dir = os.path.join(BASE_DIR, app_id)
    branches = [req.branch] if req.branch != 'main' else ['main', 'master']
    for br in branches:
        try:
            Repo.clone_from(req.repo_url, app_dir, branch=br)
            return GitCloneResponse(app_id=app_id, cloned_branch=br)
        except GitCommandError:
            continue
    if os.path.isdir(app_dir):
        shutil.rmtree(app_dir, ignore_errors=True)
    raise HTTPException(status_code=500, detail="Failed to clone repository")

@app.post("/suggestions", response_model=AISuggestionResponse)
async def ai_code_analysis(app_id: str):
    if not openai_client:
        raise HTTPException(status_code=503, detail="AI service unavailable")

    app_dir = os.path.join(BASE_DIR, app_id)
    if not os.path.isdir(app_dir):
        raise HTTPException(status_code=404, detail="App not found")

    language = detect_language(app_dir)
    context = get_project_context_for_ai(app_dir, language)

    prompt = f"""
You are an expert software assistant analyzing a {language} project.

{context}

Please provide a summary, dependencies, build/run commands, and best practices.
"""

    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert software development assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=800
        )
        choice = resp.choices[0].message.content.strip()
        return AISuggestionResponse(app_id=app_id, suggestions=choice, model_used=resp.model)
    except Exception as e:
        logger.error(f"AI analysis error for {app_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
