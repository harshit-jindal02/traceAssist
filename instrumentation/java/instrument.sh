#!/bin/bash
# Java Instrumentation using OpenTelemetry Java Agent

OTEL_JAR_URL="https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/latest/download/opentelemetry-javaagent.jar"

if [ ! -f "opentelemetry-javaagent.jar" ]; then
  echo "Downloading OpenTelemetry Java Agent..."
  curl -L -o opentelemetry-javaagent.jar "$OTEL_JAR_URL"
fi

echo "To run your app with instrumentation:"
echo ""
echo "java -javaagent:./opentelemetry-javaagent.jar \
  -Dotel.exporter.otlp.endpoint=http://otel-collector:4317 \
  -Dotel.resource.attributes=service.name=my-java-app \
  -jar your-app.jar"
