# utils/docker_generator.py

DOCKER_COMPOSE = '''version: '3.8'

services:
  {service_name}:
    build: .
    container_name: {service_name}
    networks:
      - telemetry
    environment:
      - OTEL_SERVICE_NAME={service_name}
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
    depends_on:
      - otel-collector

networks:
  telemetry:
    external: true
    name: telemetry_default
'''
