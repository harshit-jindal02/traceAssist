#!/usr/bin/env bash
APP_DIR=$1
cd "$APP_DIR" || exit 1

# Download the latest agent if not present
if [ ! -f "opentelemetry-javaagent.jar" ]; then
  curl -L -o opentelemetry-javaagent.jar \
    https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/latest/download/opentelemetry-javaagent.jar
fi
