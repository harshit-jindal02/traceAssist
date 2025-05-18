# backend/main.py

import os, shutil, subprocess, zipfile, uuid, requests
from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from git import Repo
from utils.docker_generator import generate_docker_files

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = "user-apps"
INSTR_DIR = "instrumentation"
os.makedirs(BASE_DIR, exist_ok=True)


class GitCloneRequest(BaseModel):
    repo_url: str
    branch: Optional[str] = "main"


class InstrumentRequest(BaseModel):
    app_id: str


def detect_language(app_path: str) -> str:
    files = os.listdir(app_path)
    if "package.json" in files: return "node"
    if any(f.endswith(".py") for f in files): return "python"
    if any(f.endswith(".java") or f.endswith(".jar") for f in files): return "java"
    return "unknown"


@app.post("/upload")
async def upload_zip(file: UploadFile = File(...)):
    app_id = str(uuid.uuid4())
    app_dir = os.path.join(BASE_DIR, app_id)
    os.makedirs(app_dir, exist_ok=True)
    zip_path = os.path.join(app_dir, "app.zip")
    with open(zip_path, "wb") as b: shutil.copyfileobj(file.file, b)
    with zipfile.ZipFile(zip_path, "r") as z: z.extractall(app_dir)
    os.remove(zip_path)
    return {"app_id": app_id}


@app.post("/clone")
async def clone_repo(req: GitCloneRequest):
    app_id = str(uuid.uuid4())
    app_dir = os.path.join(BASE_DIR, app_id)
    os.makedirs(app_dir, exist_ok=True)
    try:
        Repo.clone_from(req.repo_url, app_dir, branch=req.branch)
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"app_id": app_id}


@app.post("/instrument")
async def instrument_app(req: InstrumentRequest):
    app_dir = os.path.join(BASE_DIR, req.app_id)
    if not os.path.isdir(app_dir):
        raise HTTPException(404, "App not found")
    lang = detect_language(app_dir)
    if lang == "unknown":
        raise HTTPException(400, "Unsupported language")
    script = os.path.join(INSTR_DIR, lang, "setup.sh")
    if not os.path.isfile(script):
        raise HTTPException(500, f"No instrumentation script for '{lang}'")
    try:
        subprocess.run(
            ["bash", script, app_dir],
            check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            500,
            f"Instrumentation failed:\nSTDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}"
        )
    gen = generate_docker_files(req.app_id)
    if "error" in gen:
        raise HTTPException(500, gen["error"])
    return {"message": "Instrumented", "compose": gen["compose"]}


@app.post("/run")
async def run_container(req: InstrumentRequest):
    compose = os.path.join(BASE_DIR, req.app_id, "docker-compose.user.yml")
    if not os.path.isfile(compose):
        raise HTTPException(404, "Compose file not found")
    try:
        subprocess.run(
            ["docker-compose", "-f", compose, "up", "-d"],
            check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            500,
            f"Run failed:\nSTDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}"
        )
    return {"message": "Container started"}


@app.get("/suggestions")
async def proxy_suggestions(app_id: str = Query(...)):
    """
    GET /suggestions?app_id=...
    Proxies to POST http://localhost:8200/suggest
    """
    try:
        ai_resp = requests.post(
            "http://localhost:8200/suggest",
            json={"app_id": app_id},
            timeout=5
        )
        ai_resp.raise_for_status()
    except requests.RequestException as e:
        detail = str(e)
        if e.response is not None:
            detail = f"{e.response.status_code} {e.response.text}"
        raise HTTPException(502, f"AI-agent error: {detail}")
    return ai_resp.json()
