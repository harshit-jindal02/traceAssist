import os
import shutil
import zipfile
import uuid
import subprocess
import logging

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import Optional, Any

from git import Repo, GitCommandError
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader
from openai import OpenAI, APIConnectionError, RateLimitError, APIStatusError

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# Load environment
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# OpenTelemetry setup
OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", os.getenv("SIGNOZ_CLOUD_ENDPOINT"))
SERVICE_NAME = "traceassist-backend"
resource = Resource.create({"service.name": SERVICE_NAME})
provider = TracerProvider(resource=resource)
exporter = OTLPSpanExporter(endpoint=OTEL_ENDPOINT, insecure=True)
provider.add_span_processor(BatchSpanProcessor(exporter))
trace.set_tracer_provider(provider)

# FastAPI setup
app = FastAPI()
FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Directories
BASE_DIR = "user-apps"
TEMPLATE_DIR = "templates"
os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(TEMPLATE_DIR, exist_ok=True)
os.makedirs("k8s", exist_ok=True)

# Models
class GitCloneRequest(BaseModel):
    repo_url: str
    branch: Optional[str] = Field(default="main")
    @validator("branch", pre=True, always=True)
    def norm_branch(cls, v):
        return "main" if v is None or v == "master" else v

class InstrumentRequest(BaseModel):
    app_id: str

class AISuggestionResponse(BaseModel):
    app_id: str
    suggestions: str
    model_used: Optional[str]

# Language detection
def detect_language(path: str) -> str:
    has_pkg = False; py = java = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in (".git","node_modules","__pycache__","venv")]
        if "package.json" in files: has_pkg = True
        py   += sum(1 for f in files if f.endswith(".py"))
        java += sum(1 for f in files if f.endswith(".java"))
    if has_pkg:             return "nodejs"
    if py>0 and java==0:    return "python"
    if java>0:              return "java"
    return "unknown"

PORT_MAP = {"nodejs":3000, "python":8000, "java":8080}

# Generate Dockerfile per language
def generate_dockerfile(path: str, language: str, port: int):
    if language == "nodejs":
        df = f"""FROM node:16
WORKDIR /app
COPY . .
RUN npm install
EXPOSE {port}
CMD [ "npm", "start" ]"""
    elif language == "python":
        df = f"""FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt python-dotenv
COPY . .
EXPOSE {port}
CMD [ "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "{port}" ]"""
    elif language == "java":
        df = f"""FROM maven:3.8-openjdk-17 AS build
WORKDIR /app
COPY . .
RUN mvn package -DskipTests

FROM openjdk:17-jdk-slim
WORKDIR /app
COPY --from=build /app/target/*.jar app.jar
EXPOSE {port}
CMD [ "java", "-jar", "app.jar" ]"""
    else:
        raise HTTPException(400, f"Unsupported language for Dockerfile: {language}")
    with open(os.path.join(path, "Dockerfile"), "w") as f:
        f.write(df)

# Build user image
def build_user_image(app_id: str, source_dir: str, language: str, port: int) -> str:
    image_name = f"user-app-{app_id}:latest"
    logger.info("Generating Dockerfile for %s in %s", language, source_dir)
    generate_dockerfile(source_dir, language, port)
    logger.info("Building Docker image %s", image_name)
    subprocess.run(["docker", "build", "-t", image_name, source_dir], check=True)
    return image_name

# Endpoints
@app.post("/upload")
async def upload_zip(file: UploadFile=File(...)):
    app_id = str(uuid.uuid4()); app_dir = os.path.join(BASE_DIR, app_id)
    os.makedirs(app_dir, exist_ok=True)
    try:
        zf = os.path.join(app_dir, "app.zip")
        with open(zf, "wb") as buf: shutil.copyfileobj(file.file, buf)
        with zipfile.ZipFile(zf, "r") as z: z.extractall(app_dir)
        os.remove(zf)
    except Exception as e:
        shutil.rmtree(app_dir, ignore_errors=True)
        raise HTTPException(500, str(e))
    return {"app_id": app_id}

@app.post("/clone")
async def clone_repo(req: GitCloneRequest):
    app_id = str(uuid.uuid4()); app_dir = os.path.join(BASE_DIR, app_id)
    branches = [req.branch] if req.branch!="main" else ["main","master"]
    for br in branches:
        try:
            if os.path.isdir(app_dir): shutil.rmtree(app_dir)
            Repo.clone_from(req.repo_url, app_dir, branch=br)
            return {"app_id": app_id, "cloned_branch": br}
        except GitCommandError:
            continue
    shutil.rmtree(app_dir, ignore_errors=True)
    raise HTTPException(400, "Failed to clone repository")

@app.post("/instrument")
async def instrument_app(req: InstrumentRequest):
    app_dir = os.path.join(BASE_DIR, req.app_id)
    if not os.path.isdir(app_dir):
        raise HTTPException(404, "App not found.")

    lang = detect_language(app_dir)
    port = PORT_MAP.get(lang)
    if port is None:
        raise HTTPException(400, f"Unsupported language: {lang}")

    # Build the Docker image with a generated Dockerfile
    try:
        image = build_user_image(req.app_id, app_dir, lang, port)
    except subprocess.CalledProcessError as e:
        logger.error("Image build failed: %s", e)
        raise HTTPException(500, f"Image build failed: {e}")

    # Render & apply k8s manifests
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    context = {"app_id": req.app_id, "image": image, "port": port, "language": lang}
    for tmpl, out in [("deployment.yaml.j2", f"{req.app_id}-deployment.yaml"),
                      ("service.yaml.j2",    f"{req.app_id}-service.yaml")]:
        content = env.get_template(tmpl).render(**context)
        path = os.path.join("k8s", out)
        with open(path, "w") as f:
            f.write(content)
        try:
            subprocess.run(["kubectl", "apply", "-n", "traceassist", "-f", path],
                           check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode()
            logger.error("kubectl apply failed: %s", stderr)
            raise HTTPException(500, f"Failed to apply {out}: {stderr}")

    return {"message": "Instrumented & deployed", "app_id": req.app_id}

@app.post("/run")
async def run_app(req: InstrumentRequest):
    return {"message":"Application is deployed"}

@app.post("/suggestions", response_model=AISuggestionResponse)
async def ai_suggestions(req: InstrumentRequest):
    if not openai_client:
        raise HTTPException(503, "AI unavailable")
    prompt = f"Observability suggestions for user-app-{req.app_id}"
    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role":"system","content":"You are an observability expert."},
                {"role":"user","content":prompt}
            ],
            temperature=0.3, max_tokens=500
        )
        txt = resp.choices[0].message.content.strip()
        return AISuggestionResponse(app_id=req.app_id, suggestions=txt, model_used=resp.model)
    except (APIConnectionError, RateLimitError, APIStatusError) as e:
        logger.error("AI error %s", e)
        raise HTTPException(500, str(e))
