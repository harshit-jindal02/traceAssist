#!/usr/bin/env bash
APP_DIR=$1
cd "$APP_DIR" || exit 1

# Install OTel libs
npm install @opentelemetry/api @opentelemetry/sdk-node @opentelemetry/auto-instrumentations-node \
            @opentelemetry/exporter-trace-otlp-grpc

# Generate wrapper
cat > instrumentation.js <<'EOF'
const { NodeSDK } = require('@opentelemetry/sdk-node');
const { getNodeAutoInstrumentations } = require('@opentelemetry/auto-instrumentations-node');
const sdk = new NodeSDK({
  traceExporter: new (require('@opentelemetry/exporter-trace-otlp-grpc').OTLPTraceExporter)({
    url: 'http://otel-collector:4317',
  }),
  instrumentations: [getNodeAutoInstrumentations()],
});
sdk.start().then(() => require('./index.js'));
EOF
