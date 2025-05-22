# backend/Dockerfile
FROM python:3.10-slim
WORKDIR /app

# Copy requirements.txt from backend/ into /app
COPY requirements.txt .

# Install deps
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your FastAPI code
COPY . .

# Run the server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
