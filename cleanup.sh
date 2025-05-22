#!/usr/bin/env bash
set -e

echo "🗑️  Uninstalling SigNoz…"
helm uninstall signoz -n signoz || true
kubectl delete namespace signoz || true

echo "🗑️  Deleting TraceAssist resources…"
kubectl delete namespace traceassist || true

echo "✅ Cleaned up."
