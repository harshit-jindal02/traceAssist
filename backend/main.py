import os
import shutil
import subprocess
import zipfile
import uuid
# import requests # Not used in the provided snippet
import logging

from fastapi import FastAPI, File, UploadFile, HTTPException # Query not used
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import Optional, Any
# from urllib.parse import urlparse, urlunparse # No longer needed for token injection
from git import Repo, GitCommandError

from utils.docker_generator import generate_docker_files

# Added OpenAI imports for v1.0+
from openai import OpenAI, APIConnectionError, RateLimitError, APIStatusError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

# OpenAI Client Initialization (remains the same)
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
    repo_url: str = Field(..., description="The HTTPS URL of the repository (e.g., https://github.com/user/repo.git)")
    branch: Optional[str] = Field(default="main", description="The branch to clone. Defaults to 'main'. 'master' is normalized to 'main'.")
    # token field is REMOVED

    @validator("branch", pre=True, always=True)
    @classmethod
    def normalize_default_branch(cls, v: Any) -> str:
        if v is None:
            logger.debug("Branch input is None, defaulting to 'main'.")
            return "main"
        if isinstance(v, str):
            original_v = v
            v = v.strip()
            if not v: # Handle empty string
                logger.debug("Branch input is empty or whitespace, defaulting to 'main'.")
                return "main"
            if v == "master":
                logger.debug("Branch input 'master' normalized to 'main'.")
                return "main"
            logger.debug(f"Branch input '{original_v}' (processed as '{v}') accepted.")
            return v
        logger.error(f"Invalid branch type: {type(v).__name__}. Must be a string or None.")
        raise TypeError(f"Branch must be a string or None; got {type(v).__name__}")

    @validator("repo_url")
    @classmethod
    def validate_repo_url_is_https(cls, v: str) -> str:
        if not v:
            raise ValueError("repo_url cannot be empty.")
        if not v.startswith("https://"):
            raise ValueError("repo_url must be an HTTPS URL (e.g., https://github.com/user/repo.git).")
        return v

    # The url_for_cloning property is removed as the application no longer injects tokens.
    # Git will use the repo_url directly and rely on a configured credential manager.

class InstrumentRequest(BaseModel): 
    app_id: str

class AISuggestionResponse(BaseModel): 
    app_id: str
    suggestions: str
    model_used: Optional[str] = None

# --- Helper Functions ---
def detect_language(app_path: str) -> str: 
    has_package_json = False
    py_count = 0
    java_count = 0
    jar_count = 0

    if not os.path.isdir(app_path):
        logger.warning(f"Path provided to detect_language is not a directory: {app_path}")
        return "unknown"

    for root, dirs, files in os.walk(app_path):
        
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
    if py_count > 0 and java_count == 0: 
        return "python"
    if java_count > 0 or jar_count > 0: 
        return "java"
    if py_count > 0: 
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

    # The token is no longer part of the request (req.token does not exist)
    logger.info(f"Cloning: {req.repo_url}, Branch: {req.branch}. Authentication will rely on server-side Git Credential Manager.")

    # The URL to clone is directly from the request, assuming it's a plain HTTPS URL
    url_to_clone = req.repo_url

    # Your existing branch trying logic is good
    branches_to_try = ["main", "master"] if req.branch == "main" else [req.branch]

    last_git_error_stderr = "" # To store specific git error messages

    for branch in branches_to_try:
        try:
            logger.info(f"Attempting to clone app_id: {app_id}, URL: {url_to_clone}, Branch: {branch} into {app_dir}")
            if os.path.exists(app_dir):
                shutil.rmtree(app_dir)
            os.makedirs(app_dir, exist_ok=True)

            # Repo.clone_from will use the system's git, which should use the GCM
            Repo.clone_from(url_to_clone, app_dir, branch=branch)

            logger.info(f"Successfully cloned '{req.repo_url}' on branch '{branch}' into {app_dir}")
            return {"app_id": app_id, "cloned_branch": branch}

        except GitCommandError as e:
            # Log the stderr from GitCommandError, which often contains useful info
            # exc_info=False because we are logging e.stderr which is the primary info here
            logger.error(f"GitCommandError while cloning {url_to_clone} (branch: {branch}): {e.stderr}", exc_info=False)
            last_git_error_stderr = e.stderr or str(e) # Store the error message

            # If auth failed or repo not found, GCM likely couldn't help or repo is truly inaccessible
            # No need to try other branches if the fundamental access is the issue
            if "authentication failed" in str(e).lower() or \
               "repository not found" in str(e).lower() or \
               "could not read Username" in str(e): # Common GCM interaction failure message
                logger.warning(f"Stopping clone attempts for {url_to_clone} due to auth/not found error on branch {branch}.")
                break # Stop trying other branches
            # If "not found" is related to the branch itself, continue to try other branches
            elif "not found" in str(e).lower() : # Could be "branch not found"
                logger.info(f"Branch '{branch}' not found for {url_to_clone}, trying next.")
                continue
            else: # Other Git error, treat as fatal for this attempt, but might not be auth related
                break 
        except Exception as e:
            logger.exception(f"Unexpected error during cloning of {url_to_clone} (branch: {branch}).")
            raise HTTPException(status_code=500, detail=f"Unexpected error during cloning: {str(e)}")

    # If loop finishes without returning, cloning failed
    detail_msg = f"Failed to clone from repository {req.repo_url} on branch(es): {', '.join(branches_to_try)}."
    if last_git_error_stderr:
        # Provide more specific feedback if possible
        if "authentication failed" in last_git_error_stderr.lower():
            detail_msg = f"Authentication failed for {req.repo_url}. Ensure the server's Git Credential Manager is configured correctly with valid credentials (e.g., PAT)."
        elif "repository not found" in last_git_error_stderr.lower():
            detail_msg = f"Repository {req.repo_url} not found or access denied."
        else:
            # Add the raw error if it's not one of the common ones already handled
            detail_msg += f" Last Git error: {last_git_error_stderr}"
    
    logger.error(f"All clone attempts failed for {req.repo_url}. Final detail: {detail_msg}")
    # Use 404 if it's likely a "not found" issue (repo or branch), 500 or 403 for auth/other server issues
    status_code = 404 
    if "authentication failed" in detail_msg.lower():
        status_code = 403 # Forbidden due to auth
    elif "Last Git error" in detail_msg and "repository not found" not in detail_msg.lower() and "branch" not in detail_msg.lower() :
        status_code = 500 # Potentially a server-side git issue

    if os.path.exists(app_dir): # Clean up failed clone attempt directory
        shutil.rmtree(app_dir, ignore_errors=True)

    raise HTTPException(status_code=status_code, detail=detail_msg)

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
        
        stdout_msg = e.stdout.decode(errors='ignore') if e.stdout else "N/A"
        stderr_msg = e.stderr.decode(errors='ignore') if e.stderr else "N/A"
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
            check=True, capture_output=True, text=True, timeout=240 
        )
        logger.info(f"Docker Compose STDOUT for {req.app_id}:\n{process.stdout}")
        if process.stderr:
             logger.warning(f"Docker Compose STDERR for {req.app_id}:\n{process.stderr}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Docker Compose run failed for app {req.app_id}:\nSTDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start container(s):\nSTDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}")
    except subprocess.TimeoutExpired as e:
        stdout_msg = e.stdout.decode(errors='ignore') if e.stdout else "N/A"
        stderr_msg = e.stderr.decode(errors='ignore') if e.stderr else "N/A"
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
            model="gpt-4o", # Or your preferred model
            messages=[
                {"role": "system", "content": "You are an expert software development assistant providing concise and practical advice."},
                {"role": "user", "content": prompt}
            ],
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
