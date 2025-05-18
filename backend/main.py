import os
import shutil
import subprocess
import zipfile
import uuid
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from git import Repo

app = FastAPI()

BASE_DIR = "user-apps"
INSTRUMENTATION_DIR = "instrumentation"
os.makedirs(BASE_DIR, exist_ok=True)


# ------------ Models ------------

class GitCloneRequest(BaseModel):
    repo_url: str
    branch: Optional[str] = "main"

class InstrumentRequest(BaseModel):
    app_id: str


# ------------ Helpers ------------

def detect_language(app_path: str) -> str:
    files = os.listdir(app_path)
    if "package.json" in files:
        return "node"
    elif any(f.endswith(".py") for f in files):
        return "python"
    elif any(f.endswith(".java") or f.endswith(".jar") for f in files):
        return "java"
    return "unknown"

def generate_docker_files(app_id: str):
    app_dir = os.path.join(BASE_DIR, app_id)
    lang = detect_language(app_dir)
    dockerfile_path = os.path.join(app_dir, "Dockerfile")
    compose_path = os.path.join(app_dir, "docker-compose.user.yml")

    service_name = f"userapp-{app_id[:8]}"

    dockerfile_content = ""
    command = ""

    if lang == "python":
        dockerfile_content = f"""
FROM python:3.9
WORKDIR /app
COPY . /app
RUN pip install -r requirements.txt
ENV OTEL_SERVICE_NAME={service_name}
ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
CMD ["python", "main.py"]
        """.strip()
    elif lang == "node":
        dockerfile_content = f"""
FROM node:18
WORKDIR /app
COPY . /app
RUN npm install
ENV OTEL_SERVICE_NAME={service_name}
ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
CMD ["node", "index.js"]
        """.strip()
    elif lang == "java":
        dockerfile_content = f"""
FROM openjdk:17
WORKDIR /app
COPY . /app
ENV OTEL_SERVICE_NAME={service_name}
ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
CMD ["java", "-javaagent:otel/opentelemetry-javaagent.jar", "-jar", "app.jar"]
        """.strip()
    else:
        return {"error": f"Unsupported language: {lang}"}

    docker_compose_content = f"""
version: "3.8"
services:
  {service_name}:
    build: .
    container_name: {service_name}
    networks:
      - telemetry
    environment:
      - OTEL_SERVICE_NAME={service_name}
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
    depends_on:
      - otel-collector

networks:
  telemetry:
    external: true
    name: telemetry_default
    """.strip()

    try:
        with open(dockerfile_path, "w") as df:
            df.write(dockerfile_content)
        with open(compose_path, "w") as dc:
            dc.write(docker_compose_content)
    except Exception as e:
        return {"error": f"Failed to write Docker files: {str(e)}"}

    return {"message": "Dockerfile and docker-compose written"}


# ------------ API Routes ------------

@app.post("/upload")
async def upload_zip(file: UploadFile = File(...)):
    app_id = str(uuid.uuid4())
    app_dir = os.path.join(BASE_DIR, app_id)
    os.makedirs(app_dir, exist_ok=True)

    zip_path = os.path.join(app_dir, "app.zip")
    with open(zip_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(app_dir)

    os.remove(zip_path)
    return {"app_id": app_id, "message": "App uploaded and extracted"}


@app.post("/clone")
def clone_repo(request: GitCloneRequest):
    app_id = str(uuid.uuid4())
    app_dir = os.path.join(BASE_DIR, app_id)
    os.makedirs(app_dir, exist_ok=True)

    try:
        Repo.clone_from(request.repo_url, app_dir, branch=request.branch)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    return {"app_id": app_id, "message": "Repo cloned"}


@app.post("/instrument")
def instrument_app(request: InstrumentRequest):
    app_dir = os.path.join(BASE_DIR, request.app_id)
    if not os.path.exists(app_dir):
        return JSONResponse(status_code=404, content={"error": "App not found"})

    lang = detect_language(app_dir)
    if lang == "unknown":
        return JSONResponse(status_code=400, content={"error": "Could not detect app language"})

    script_path = os.path.join(INSTRUMENTATION_DIR, lang, "setup.sh")
    if not os.path.exists(script_path):
        return JSONResponse(status_code=500, content={"error": f"Instrumentation script not found for {lang}"})

    try:
        subprocess.run(["bash", script_path, app_dir], check=True)
    except subprocess.CalledProcessError as e:
        return JSONResponse(status_code=500, content={"error": f"Instrumentation failed: {str(e)}"})

    docker_result = generate_docker_files(request.app_id)
    if "error" in docker_result:
        return JSONResponse(status_code=500, content=docker_result)

    return {"message": f"Instrumentation and Docker setup complete for {lang}", "language": lang}


@app.post("/run")
def run_container(request: InstrumentRequest):
    app_dir = os.path.join(BASE_DIR, request.app_id)
    compose_file = os.path.join(app_dir, "docker-compose.user.yml")

    if not os.path.exists(compose_file):
        return JSONResponse(status_code=404, content={"error": "docker-compose.user.yml not found"})

    try:
        subprocess.run(["docker-compose", "-f", compose_file, "up", "-d"], check=True)
    except subprocess.CalledProcessError as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    return {"message": "User application container started"}
