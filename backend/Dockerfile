# backend/Dockerfile
FROM python:3.10-slim

# 1. Install git for GitPython and build essentials (if you need them)
RUN apt-get update && \
    apt-get install -y git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Copy only requirements first (for better caching)
COPY requirements.txt .

# 3. Install Python deps + python-dotenv
RUN pip install --no-cache-dir -r requirements.txt python-dotenv

# 4. Copy your app code
COPY . .

# 5. Tell GitPython where git lives
ENV GIT_PYTHON_GIT_EXECUTABLE=/usr/bin/git

# 6. Start the server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
