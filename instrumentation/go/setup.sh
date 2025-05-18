#!/bin/bash

echo "🔧 Ensure OpenTelemetry Go SDK is added to your codebase."

echo "1. Install dependencies:"
echo "go get go.opentelemetry.io/otel"
echo "go get go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
echo ""

echo "2. Use sample setup for tracer provider:"
echo "https://opentelemetry.io/docs/instrumentation/go/getting-started/"

echo ""
echo "⚠️ You must modify your Go code to inject OpenTelemetry manually or use an available Go auto-instrumentation wrapper if any."
