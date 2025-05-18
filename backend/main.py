# backend/main.py

import os
import shutil
import subprocess
import zipfile
import uuid

from fastapi import FastAPI, File, UploadFile, HTTPException
from pydantic import BaseModel
from typing import Optional
from git import Repo

from utils.docker_generator import generate_docker_files

app = FastAPI()

BASE_DIR = "user-apps"
INSTRUMENTATION_DIR = "instrumentation"
os.makedirs(BASE_DIR, exist_ok=True)


class GitCloneRequest(BaseModel):
    repo_url: str
    branch: Optional[str] = "main"


class InstrumentRequest(BaseModel):
    app_id: str


def detect_language(app_path: str) -> str:
    files = os.listdir(app_path)
    if "package.json" in files:
        return "node"
    if any(f.endswith(".py") for f in files):
        return "python"
    if any(f.endswith(".java") or f.endswith(".jar") for f in files):
        return "java"
    return "unknown"


@app.post("/upload")
async def upload_zip(file: UploadFile = File(...)):
    """Upload a ZIP, extract it, and return an app_id."""
    app_id = str(uuid.uuid4())
    app_dir = os.path.join(BASE_DIR, app_id)
    os.makedirs(app_dir, exist_ok=True)

    zip_path = os.path.join(app_dir, "app.zip")
    with open(zip_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(app_dir)
    os.remove(zip_path)

    return {"app_id": app_id, "message": "App uploaded and extracted"}


@app.post("/clone")
def clone_repo(request: GitCloneRequest):
    """Clone a GitHub repo and return an app_id."""
    app_id = str(uuid.uuid4())
    app_dir = os.path.join(BASE_DIR, app_id)
    os.makedirs(app_dir, exist_ok=True)

    try:
        Repo.clone_from(request.repo_url, app_dir, branch=request.branch)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"app_id": app_id, "message": "Repo cloned"}


@app.post("/instrument")
def instrument_app(request: InstrumentRequest):
    """
    1) Detect the app language
    2) Run the language-specific setup.sh
    3) Generate Dockerfile + docker-compose.user.yml
    """
    app_dir = os.path.join(BASE_DIR, request.app_id)
    if not os.path.isdir(app_dir):
        raise HTTPException(status_code=404, detail="App not found")

    lang = detect_language(app_dir)
    if lang == "unknown":
        raise HTTPException(status_code=400, detail="Unsupported language")

    script = os.path.join(INSTRUMENTATION_DIR, lang, "setup.sh")
    if not os.path.isfile(script):
        raise HTTPException(status_code=500, detail=f"No instrumentation script for '{lang}'")

    # Run instrumentation
    try:
        subprocess.run(["bash", script, app_dir], check=True)
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Instrumentation failed: {e}")

    # Generate Docker files
    result = generate_docker_files(request.app_id)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return {
        "message": f"Instrumented & Docker files created for '{lang}'",
        "language": lang,
        "dockerfile": result["dockerfile"],
        "compose": result["compose"],
    }


@app.post("/run")
def run_container(request: InstrumentRequest):
    """Start the user app container using docker-compose.user.yml."""
    app_dir = os.path.join(BASE_DIR, request.app_id)
    compose_file = os.path.join(app_dir, "docker-compose.user.yml")
    if not os.path.isfile(compose_file):
        raise HTTPException(status_code=404, detail="Compose file not found")

    try:
        subprocess.run(["docker-compose", "-f", compose_file, "up", "-d"], check=True)
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Run failed: {e}")

    return {"message": "User application container started"}
