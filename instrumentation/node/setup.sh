#!/usr/bin/env bash
set -e

APP_DIR="$1"
cd "$APP_DIR"

# Install dependencies
npm install
npm install --save \
  @opentelemetry/api \
  @opentelemetry/sdk-node \
  @opentelemetry/auto-instrumentations-node \
  @opentelemetry/exporter-trace-otlp-grpc

# Generate a Bootstrapper
cat > instrumentation.js << 'EOF'
'use strict';

const { NodeSDK } = require('@opentelemetry/sdk-node');
const { getNodeAutoInstrumentations } = require('@opentelemetry/auto-instrumentations-node');
const { OTLPTraceExporter } = require('@opentelemetry/exporter-trace-otlp-grpc');

// Configure the SDK
const sdk = new NodeSDK({
  traceExporter: new OTLPTraceExporter({
    url: 'http://otel-collector:4317',
    // you can add headers/auth here if needed
  }),
  instrumentations: [ getNodeAutoInstrumentations() ],
});

// Start SDK _without_ chaining .then()
sdk.start();

// Hand off to the user's main file
console.log('✅ OpenTelemetry SDK initialized');
require('./index.js');
EOF

chmod +x instrumentation.js
