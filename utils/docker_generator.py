import os
import shutil

DOCKERFILES = {
    "python": '''FROM python:3.9

WORKDIR /app
COPY . .

RUN pip install -r requirements.txt
RUN pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp \
    opentelemetry-instrumentation opentelemetry-instrumentation-flask \
    opentelemetry-instrumentation-requests

CMD ["opentelemetry-instrument", "--traces_exporter", "otlp", "--metrics_exporter", "otlp", "--logs_exporter", "otlp", "--", "python", "main.py"]
''',

    "node": '''FROM node:18

WORKDIR /app
COPY . .

RUN npm install
RUN npm install @opentelemetry/api @opentelemetry/sdk-node \
    @opentelemetry/auto-instrumentations-node \
    @opentelemetry/exporter-trace-otlp-grpc

COPY instrumentation.js ./instrumentation.js

CMD ["node", "-r", "./instrumentation.js", "index.js"]
''',

    "java": '''FROM openjdk:17

WORKDIR /app
COPY . .

COPY opentelemetry-javaagent.jar /app/opentelemetry-javaagent.jar

CMD ["java", "-javaagent:/app/opentelemetry-javaagent.jar", "-jar", "app.jar"]
'''
}

DOCKER_COMPOSE = '''version: '3.8'

services:
  user-app:
    build: .
    ports:
      - "8080:8080"
    environment:
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
      - OTEL_RESOURCE_ATTRIBUTES=service.name={service_name}
    depends_on:
      - otel-collector

networks:
  default:
    name: telemetry_default
    external: true
'''

def detect_language(app_path: str) -> str:
    if os.path.exists(os.path.join(app_path, "package.json")):
        return "node"
    elif any(fname.endswith(".py") for fname in os.listdir(app_path)):
        return "python"
    elif any(fname.endswith(".jar") or fname.endswith(".java") for fname in os.listdir(app_path)):
        return "java"
    else:
        return "unknown"

def generate_docker_files(app_id: str, base_dir="user-apps") -> dict:
    app_path = os.path.join(base_dir, app_id)
    language = detect_language(app_path)
    
    if language == "unknown":
        return {"error": "Unsupported application language."}

    # Write Dockerfile
    with open(os.path.join(app_path, "Dockerfile"), "w") as f:
        f.write(DOCKERFILES[language])

    # Write docker-compose.user.yml
    compose_path = os.path.join(app_path, "docker-compose.user.yml")
    with open(compose_path, "w") as f:
        f.write(DOCKER_COMPOSE.format(service_name=f"user-app-{app_id}"))

    return {
        "language": language,
        "dockerfile": os.path.join(app_path, "Dockerfile"),
        "compose": compose_path
    }
