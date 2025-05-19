import os
import shutil
import subprocess
import zipfile
import uuid
import requests 
import logging 

from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import Optional, Any

from git import Repo, GitCommandError 

from utils.docker_generator import generate_docker_files 

# Added OpenAI imports for v1.0+
from openai import OpenAI, APIConnectionError, RateLimitError, APIStatusError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

# OpenAI Client Initialization
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY environment variable not set. AI features will not work.")
    openai_client = None
else:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

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

# --- Pydantic Models ---
class GitCloneRequest(BaseModel):
    repo_url: str
    branch: Optional[str] = Field(default="main")

    @validator("branch", pre=True, always=True)
    @classmethod
    def normalize_default_branch(cls, v: Any) -> str:
        if v is None:  
            return "main"
        if v == "master": 
            return "main"
        if isinstance(v, str): 
            return v
        raise TypeError(f"Branch must be a string; got {type(v).__name__}")

class InstrumentRequest(BaseModel): # Also used for AI analysis request
    app_id: str

class AISuggestionResponse(BaseModel): # New model for AI response
    app_id: str
    suggestions: str
    model_used: Optional[str] = None

# --- Helper Functions ---
def detect_language(app_path: str) -> str: # Updated version
    has_package_json = False
    py_count = 0
    java_count = 0
    jar_count = 0

    if not os.path.isdir(app_path):
        logger.warning(f"Path provided to detect_language is not a directory: {app_path}")
        return "unknown"

    for root, dirs, files in os.walk(app_path):
        # Exclude common virtual environment and dependency folders from scan
        dirs[:] = [d for d in dirs if d not in ['.git', 'node_modules', '__pycache__', 'venv', 'env', '.venv', 'target', 'build', 'dist']]
        if "package.json" in files:
            has_package_json = True
        for f_name in files: 
            if f_name.endswith(".py"):
                py_count += 1
            if f_name.endswith(".java"):
                java_count += 1
            if f_name.endswith(".jar"):
                jar_count += 1

    if has_package_json:
        return "node"
    # Refined priority for detection
    if py_count > 0 and java_count == 0: # Primarily Python
        return "python"
    if java_count > 0 or jar_count > 0: # Primarily Java (source or JARs)
        return "java"
    if py_count > 0: # Fallback to Python if some .py files exist
        return "python"
    return "unknown"

# New helper function to get project context for AI
MAX_CONTEXT_FILES_AI = 7  # Max files to read content from
MAX_FILE_SIZE_AI_BYTES = 15 * 1024  # 15 KB per file
MAX_TOTAL_CONTENT_AI_CHARS = 12000 # Approx 3k-4k tokens, safe for gpt-3.5-turbo 4k limit

def get_project_context_for_ai(app_path: str, language: str) -> str:
    context_parts = []
    current_chars_count = 0
    files_read_count = 0

    # 1. File tree (limited)
    tree_str = "Project structure (partial):\n"
    tree_lines = 0
    max_tree_lines = 25
    for root, dirs, files in os.walk(app_path):
        dirs[:] = [d for d in dirs if d not in ['.git', 'node_modules', '__pycache__', 'venv', 'env', '.venv', 'target', 'build', 'dist', '.DS_Store']]
        files = [f for f in files if f not in ['.DS_Store']]
        
        level = root.replace(app_path, '').count(os.sep)
        if level > 3: # Limit directory depth in tree
            dirs[:] = [] # Don't look deeper
            continue

        indent = "  " * level
        if tree_lines < max_tree_lines:
            tree_str += f"{indent}{os.path.basename(root) or '.'}/\n"
            tree_lines +=1
        
        for f_name in files[:4]: # Limit files per dir in tree display
            if tree_lines < max_tree_lines:
                tree_str += f"{indent}  {f_name}\n"
                tree_lines += 1
            else: break
        if tree_lines >= max_tree_lines:
            tree_str += f"{indent}  ... (more files/dirs)\n"
            break 
    
    if tree_lines > 0 :
        context_parts.append(tree_str)
        current_chars_count += len(tree_str)

    # 2. Key file contents
    primary_key_files_map = {
        "node": ["package.json"],
        "python": ["requirements.txt", "pyproject.toml", "setup.py"],
        "java": ["pom.xml", "build.gradle"],
    }
    secondary_key_files_map = {
        "node": ["server.js", "app.js", "index.js", "vite.config.js", "next.config.js"],
        "python": ["main.py", "app.py", "wsgi.py", "asgi.py"],
        "java": ["Main.java", "Application.java", "application.properties", "application.yml"],
    }
    
    candidate_files_ordered = [("README.md", "README.md")] 
    for fname in primary_key_files_map.get(language, []): candidate_files_ordered.append((fname, fname))
    for fname in secondary_key_files_map.get(language, []): candidate_files_ordered.append((fname, fname))

    processed_paths = set()
    
    def read_and_append(file_path, display_name_hint):
        nonlocal current_chars_count, files_read_count
        if files_read_count >= MAX_CONTEXT_FILES_AI or current_chars_count >= MAX_TOTAL_CONTENT_AI_CHARS:
            return False 

        try:
            file_size = os.path.getsize(file_path)
            if 0 < file_size <= MAX_FILE_SIZE_AI_BYTES:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(MAX_FILE_SIZE_AI_BYTES) # Read up to max size
                
                rel_path = os.path.relpath(file_path, app_path)
                header = f"\n--- Content of {rel_path} ---\n"
                
                if current_chars_count + len(content) + len(header) < MAX_TOTAL_CONTENT_AI_CHARS:
                    context_parts.append(header + content)
                    current_chars_count += len(content) + len(header)
                    files_read_count += 1
                    processed_paths.add(file_path)
                    return True
                else: 
                    if files_read_count > 0: return False 
        except Exception as e:
            logger.warning(f"Could not read file {file_path} for AI context: {e}")
        return True 

    for root, dirs, files in os.walk(app_path, topdown=True):
        dirs[:] = [d for d in dirs if d not in ['.git', 'node_modules', '__pycache__', 'venv', 'env', '.venv', 'target', 'build', 'dist', '.DS_Store']]
        
        for cf_name, display_hint in candidate_files_ordered:
            if cf_name in files:
                file_path = os.path.join(root, cf_name)
                if file_path not in processed_paths:
                    if not read_and_append(file_path, display_hint): break 
        if files_read_count >= MAX_CONTEXT_FILES_AI or current_chars_count >= MAX_TOTAL_CONTENT_AI_CHARS: break
    
    source_extensions = {
        "python": [".py"], "node": [".js", ".jsx", ".ts", ".tsx"], "java": [".java"]
    }.get(language, [])

    if source_extensions and files_read_count < MAX_CONTEXT_FILES_AI and current_chars_count < MAX_TOTAL_CONTENT_AI_CHARS:
        for root, dirs, files in os.walk(app_path, topdown=True):
            dirs[:] = [d for d in dirs if d not in ['.git', 'node_modules', '__pycache__', 'venv', 'env', '.venv', 'target', 'build', 'dist', '.DS_Store']]
            files.sort(key=lambda name: (len(name), name)) 

            for f_name in files:
                if any(f_name.endswith(ext) for ext in source_extensions):
                    file_path = os.path.join(root, f_name)
                    if file_path not in processed_paths:
                        if root.replace(app_path, '').count(os.sep) <= 2: # Prefer files not too deep
                            if not read_and_append(file_path, f_name): break 
            if files_read_count >= MAX_CONTEXT_FILES_AI or current_chars_count >= MAX_TOTAL_CONTENT_AI_CHARS: break
                
    if not context_parts:
        return "No readable project files found or project is empty; cannot provide AI analysis."
        
    final_context = "".join(context_parts) 
    logger.info(f"Generated AI context: ~{current_chars_count} chars, {files_read_count} files for app path {app_path}.")
    return final_context

# --- API Endpoints ---
@app.post("/upload")
async def upload_zip(file: UploadFile = File(...)):
    app_id = str(uuid.uuid4())
    app_dir = os.path.join(BASE_DIR, app_id)
    os.makedirs(app_dir, exist_ok=True)
    zip_path = os.path.join(app_dir, "app.zip") 

    logger.info(f"Uploading zip for app_id: {app_id} to {zip_path}")
    try:
        with open(zip_path, "wb") as buffer: 
            shutil.copyfileobj(file.file, buffer)
        logger.info(f"Zip file saved: {zip_path}")
        with zipfile.ZipFile(zip_path, "r") as z_ref: 
            z_ref.extractall(app_dir)
        logger.info(f"Zip file extracted to: {app_dir}")
        os.remove(zip_path)
        logger.info(f"Zip file removed: {zip_path}")
    except Exception as e:
        logger.error(f"Error during zip upload/extraction for app_id {app_id}: {e}", exc_info=True)
        if os.path.exists(app_dir):
            shutil.rmtree(app_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Failed to process uploaded file: {str(e)}")
    return {"app_id": app_id}

@app.post("/clone")
async def clone_repo(req: GitCloneRequest):
    app_id = str(uuid.uuid4())
    app_dir = os.path.join(BASE_DIR, app_id)
    logger.info(f"Received clone request for URL: {req.repo_url}, branch preference from validator: {req.branch}")

    branches_to_try = []
    if req.branch == "main":
        branches_to_try.extend(["main", "master"])
    else:
        branches_to_try.append(req.branch)
    branches_to_try = list(dict.fromkeys(branches_to_try)) 

    last_exception = None
    cloned_successfully = False
    final_cloned_branch = None

    for branch_attempt in branches_to_try:
        logger.info(f"Attempting to clone {req.repo_url} with branch '{branch_attempt}' into {app_dir}")
        try:
            if os.path.exists(app_dir): shutil.rmtree(app_dir)
            os.makedirs(app_dir, exist_ok=True)
            Repo.clone_from(req.repo_url, app_dir, branch=branch_attempt)
            final_cloned_branch = branch_attempt
            logger.info(f"Successfully cloned {req.repo_url} on branch '{final_cloned_branch}' into {app_dir} (app_id: {app_id})")
            cloned_successfully = True
            break 
        except GitCommandError as e:
            last_exception = e
            logger.error(
                f"GitCommandError while cloning {req.repo_url} on branch '{branch_attempt}':\n"
                f"  Status: {e.status}\n  Command: {' '.join(e.command)}\n"
                f"  Stdout: {e.stdout.strip() if e.stdout else 'N/A'}\n  Stderr: {e.stderr.strip() if e.stderr else 'N/A'}"
            )
            stderr_lower = (e.stderr or "").lower()
            if e.status == 128 and ("repository not found" in stderr_lower or "authentication failed" in stderr_lower or "could not read username" in stderr_lower or "unable to access" in stderr_lower):
                logger.warning("Fatal git error encountered, stopping further branch attempts.")
                break 
        except Exception as e: 
            last_exception = e
            logger.error(f"Unexpected error while cloning {req.repo_url} on branch '{branch_attempt}': {str(e)}", exc_info=True)
            break 

    if not cloned_successfully:
        if os.path.exists(app_dir): shutil.rmtree(app_dir, ignore_errors=True)
        detail_message = "Failed to clone repository."
        if isinstance(last_exception, GitCommandError):
            stderr_cleaned = last_exception.stderr.strip() if last_exception.stderr else ""
            if "remote branch" in stderr_cleaned.lower() and "not found" in stderr_cleaned.lower() : 
                detail_message = f"Failed to clone: Could not find a suitable branch (tried: {', '.join(branches_to_try)}). Remote error: {stderr_cleaned}"
            elif "repository not found" in stderr_cleaned.lower():
                detail_message = f"Failed to clone: Repository not found at {req.repo_url}."
            elif "authentication failed" in stderr_cleaned.lower():
                detail_message = f"Failed to clone: Authentication failed for {req.repo_url}."
            elif "could not resolve host" in stderr_cleaned.lower():
                detail_message = f"Failed to clone: Could not resolve host for repository URL {req.repo_url}."
            else:
                detail_message = f"Git operation failed: {stderr_cleaned or str(last_exception)}"
        elif last_exception:
            detail_message = f"An unexpected error occurred: {str(last_exception)}"
        raise HTTPException(status_code=500, detail=detail_message)

    return {"app_id": app_id, "cloned_branch": final_cloned_branch}

@app.post("/instrument")
async def instrument_app(req: InstrumentRequest):
    app_dir = os.path.join(BASE_DIR, req.app_id)
    logger.info(f"Instrumenting app: {req.app_id} in dir: {app_dir}")
    if not os.path.isdir(app_dir):
        logger.error(f"App directory not found for instrumentation: {app_dir}")
        raise HTTPException(status_code=404, detail="App not found. Please upload or clone first.")

    lang = detect_language(app_dir)
    logger.info(f"Detected language for app {req.app_id}: {lang}")
    if lang == "unknown":
        logger.warning(f"Unsupported language for app {req.app_id} in {app_dir}")
        raise HTTPException(status_code=400, detail="Unsupported language or unable to detect language.")

    script_path = os.path.join(INSTR_DIR, lang, "setup.sh") 
    logger.info(f"Instrumentation script path for app {req.app_id}: {script_path}")
    if not os.path.isfile(script_path):
        logger.error(f"Instrumentation script not found for language '{lang}' at {script_path}")
        raise HTTPException(status_code=500, detail=f"No instrumentation script configured for '{lang}'")

    try:
        logger.info(f"Running instrumentation script: bash {script_path} {app_dir}")
        process = subprocess.run(
            ["bash", script_path, app_dir],
            check=True, capture_output=True, text=True, timeout=300 
        )
        logger.info(f"Instrumentation script STDOUT for {req.app_id}:\n{process.stdout}")
        if process.stderr:
             logger.warning(f"Instrumentation script STDERR for {req.app_id}:\n{process.stderr}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Instrumentation script failed for app {req.app_id}:\nSTDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Instrumentation failed:\nSTDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}")
    except subprocess.TimeoutExpired as e:
        stdout_msg = e.stdout if e.stdout else "N/A"
        stderr_msg = e.stderr if e.stderr else "N/A"
        logger.error(f"Instrumentation script timed out for app {req.app_id}:\nSTDOUT:\n{stdout_msg}\nSTDERR:\n{stderr_msg}", exc_info=True)
        raise HTTPException(status_code=500, detail="Instrumentation script timed out after 5 minutes.")
    except Exception as e:
        logger.error(f"Unexpected error during instrumentation for app {req.app_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during instrumentation: {str(e)}")

    logger.info(f"Generating Docker files for app {req.app_id}")
    try:
        gen_result = generate_docker_files(req.app_id) 
    except Exception as e:
        logger.error(f"Error calling generate_docker_files for {req.app_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate Docker files: {str(e)}")

    if isinstance(gen_result, dict) and "error" in gen_result: 
        logger.error(f"Error from generate_docker_files for {req.app_id}: {gen_result['error']}")
        raise HTTPException(status_code=500, detail=gen_result["error"])

    return {"message": "Application instrumented successfully.", "compose_file_path": gen_result.get("compose") if isinstance(gen_result, dict) else None} 

@app.post("/run")
async def run_container(req: InstrumentRequest):
    compose_file_path = os.path.join(BASE_DIR, req.app_id, "docker-compose.user.yml") 
    logger.info(f"Attempting to run Docker Compose for app {req.app_id} using {compose_file_path}")

    if not os.path.isfile(compose_file_path):
        logger.error(f"Compose file not found for app {req.app_id} at {compose_file_path}")
        raise HTTPException(status_code=404, detail="Docker Compose file not found. Ensure the app is instrumented.")

    try:
        project_dir = os.path.join(BASE_DIR, req.app_id)
        logger.info(f"Running command: docker-compose -f {compose_file_path} --project-directory {project_dir} up -d")
        process = subprocess.run(
            ["docker-compose", "-f", compose_file_path, "--project-directory", project_dir, "up", "-d"],
            check=True, capture_output=True, text=True, timeout=120 
        )
        logger.info(f"Docker Compose STDOUT for {req.app_id}:\n{process.stdout}")
        if process.stderr:
             logger.warning(f"Docker Compose STDERR for {req.app_id}:\n{process.stderr}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Docker Compose run failed for app {req.app_id}:\nSTDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start container(s):\nSTDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}")
    except subprocess.TimeoutExpired as e:
        stdout_msg = e.stdout if e.stdout else "N/A"
        stderr_msg = e.stderr if e.stderr else "N/A"
        logger.error(f"Docker Compose run timed out for app {req.app_id}:\nSTDOUT:\n{stdout_msg}\nSTDERR:\n{stderr_msg}", exc_info=True)
        raise HTTPException(status_code=500, detail="Starting container(s) timed out after 2 minutes.")
    except Exception as e:
        logger.error(f"Unexpected error during container run for app {req.app_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred while starting container(s): {str(e)}")

    return {"message": "Application container(s) started successfully."}

# --- New AI Analysis Endpoint ---
@app.post("/suggestions", response_model=AISuggestionResponse)
async def ai_code_analysis(req: InstrumentRequest):
    if not openai_client:
        logger.error("OpenAI client not configured. OPENAI_API_KEY missing.")
        raise HTTPException(status_code=503, detail="AI service unavailable: OpenAI API key not configured.")

    app_id = req.app_id
    app_dir = os.path.join(BASE_DIR, app_id)
    logger.info(f"Performing AI code analysis for app: {app_id} in dir: {app_dir}")

    if not os.path.isdir(app_dir):
        logger.error(f"App directory not found for AI analysis: {app_dir}")
        raise HTTPException(status_code=404, detail="App not found. Please upload or clone first.")

    language = detect_language(app_dir)
    logger.info(f"Detected language for AI analysis of app {app_id}: {language}")
    
    project_context = get_project_context_for_ai(app_dir, language)

    if "No readable project files" in project_context or "project is empty" in project_context :
         raise HTTPException(status_code=400, detail="Could not gather sufficient project context for AI analysis. Project might be empty or unreadable.")

    prompt_lang = language if language != "unknown" else "an undetermined language"
    prompt = f"""
    You are an expert software development assistant. Analyze the following project information for a '{prompt_lang}' application.
    The project context (partial file tree and content of key files) is provided below.

    Project Context:
    {project_context}

    Based on this context, please provide:
    1. A brief summary of the project's likely purpose and main technology stack (1-2 sentences).
    2. Key dependencies that might be required for a production build or common for this type of project.
    3. A suggested command to run or build the application, if inferable (e.g., "npm start", "python main.py", "mvn spring-boot:run").
    4. Two or three potential improvements, best practices to consider, or common pitfalls relevant to this type of project/stack.
    5. If this project were to be containerized using Docker, suggest a suitable base image (e.g., "node:18-alpine", "python:3.9-slim") and 2-3 key Dockerfile instructions (e.g., WORKDIR, COPY, RUN, CMD).

    Be concise, practical, and structure your response clearly with numbered points. If some information cannot be inferred, state that.
    """

    try:
        logger.info(f"Sending request to OpenAI for app {app_id}. Language: {language}. Context length: {len(project_context)} chars.")
        
        chat_completion = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert software development assistant providing concise and practical advice."},
                {"role": "user", "content": prompt}
            ],
            # prompt=prompt
            temperature=0.3, 
            max_tokens=800 
        )
        suggestion_text = chat_completion.choices[0].message.content.strip()
        model_used = chat_completion.model
        
        logger.info(f"Received AI suggestions for app {app_id} using model {model_used}")
        return AISuggestionResponse(app_id=app_id, suggestions=suggestion_text, model_used=model_used)

    except APIConnectionError as e:
        logger.error(f"OpenAI API connection error for app {app_id}: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"AI service connection error: {e.__class__.__name__}")
    except RateLimitError as e:
        logger.error(f"OpenAI API rate limit exceeded for app {app_id}: {e}", exc_info=True)
        raise HTTPException(status_code=429, detail=f"AI service rate limit exceeded. Please try again later.")
    except APIStatusError as e: 
        err_detail_msg = str(e)
        try:
            if e.response and e.response.content:
                err_detail_json = e.response.json()
                err_detail_msg = err_detail_json.get("error", {}).get("message", str(e))
        except Exception: # Parsing JSON failed
            pass # Keep default str(e)
            
        logger.error(f"OpenAI API status error for app {app_id}: Status {e.status_code}, Response: {e.response.text if e.response else 'N/A'}", exc_info=False) # exc_info=False to avoid verbose traceback for API errors
        raise HTTPException(status_code=e.status_code if e.status_code else 500, detail=f"AI service API error: {err_detail_msg}")
    except Exception as e:
        logger.error(f"Unexpected error during AI analysis for app {app_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during AI analysis: {str(e)}")