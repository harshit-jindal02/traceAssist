#!/usr/bin/env bash
APP_DIR=$1
cd "$APP_DIR" || exit 1

# Install app deps and OTel auto-instrument
pip install --upgrade -r requirements.txt
pip install opentelemetry-distro opentelemetry-exporter-otlp

# (Optional) Bootstrap auto-instrumentation for common libs
opentelemetry-bootstrap -a install
