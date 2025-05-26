#!/usr/bin/env bash
set -euo pipefail

# ─── Load .env (must define SIGNOZ_CLOUD_ENDPOINT and SIGNOZ_CLOUD_API_KEY) ────
if [ -f .env ]; then
  echo "🔑 Loading .env"
  set -o allexport
  source .env
  set +o allexport
fi

if [[ -z "${SIGNOZ_CLOUD_ENDPOINT:-}" || -z "${SIGNOZ_CLOUD_API_KEY:-}" ]]; then
  echo "ERROR: Please set SIGNOZ_CLOUD_ENDPOINT and SIGNOZ_CLOUD_API_KEY in .env"
  exit 1
fi

# ─── 1. Point Docker to Minikube’s daemon ──────────────────────────────────────
echo "🔧 Configuring Docker to use Minikube..."
eval "$(minikube docker-env)"

# ─── 2. Build your service images ──────────────────────────────────────────────
echo "📦 Building backend image..."
docker build -t traceassist-backend:latest backend/
echo "📦 Building AI-Agent image..."
docker build -t traceassist-ai-agent:latest ai-agent/
echo "📦 Building frontend image..."
docker build -t traceassist-frontend:latest frontend/

# ─── 3. Create namespaces ──────────────────────────────────────────────────────
echo "📂 Ensuring namespaces exist..."
kubectl create namespace signoz      --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace traceassist --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace cert-manager --dry-run=client -o yaml | kubectl apply -f -

# ─── 3.b Apply TraceAssist RBAC (Role, SA, RoleBinding) ──────────────────────
echo "🔐 Applying TraceAssist RBAC..."
kubectl -n traceassist apply -f k8s/traceassist-rbac.yaml

# ─── 4. Install cert-manager (for Operator’s webhooks) ─────────────────────────
echo "🔐 Installing cert-manager..."
kubectl apply --validate=false \
  -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml

echo "⏳ Waiting for cert-manager webhook..."
kubectl -n cert-manager rollout status deployment cert-manager-webhook --timeout=180s

# ─── 5. Install the OpenTelemetry Operator ────────────────────────────────────
echo "🔧 Installing OpenTelemetry Operator..."
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm repo update
helm upgrade --install \
  opentelemetry-operator open-telemetry/opentelemetry-operator \
  --namespace opentelemetry-operator-system --create-namespace \
  --wait --timeout=180s

# ─── 6. Apply Instrumentation CR to ship data to SigNoz Cloud ──────────────────
echo "📡 Applying Instrumentation CR..."
kubectl -n traceassist apply -f k8s/instrumentation.yaml

# ─── 7. Create secrets & deploy your TraceAssist services ──────────────────────
echo "🚀 Deploying TraceAssist services..."
kubectl -n traceassist apply \
  -f k8s/backend-secret.yaml \
  -f k8s/ai-agent-secret.yaml \
  -f k8s/backend-deployment.yaml \
  -f k8s/backend-service.yaml \
  -f k8s/ai-agent-deployment.yaml \
  -f k8s/ai-agent-service.yaml \
  -f k8s/frontend-deployment.yaml \
  -f k8s/frontend-service.yaml

# ─── 8. Restart deployments to pick up new secrets/env vars ────────────────────
echo "🔄 Restarting backend and AI-Agent deployments..."
kubectl -n traceassist rollout restart deployment traceassist-backend
kubectl -n traceassist rollout restart deployment traceassist-ai-agent

# ─── 9. Done! ───────────────────────────────────────────────────────────────
echo
echo "✅ All components are up."
echo
echo "🔗 TraceAssist UI:"
echo "   kubectl -n traceassist port-forward svc/traceassist-frontend 5173:5173"
echo "   open http://localhost:5173"
echo
echo "🌩️  SigNoz Cloud ingestion endpoint:"
echo "   ${SIGNOZ_CLOUD_ENDPOINT}"