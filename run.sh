#!/usr/bin/env bash
set -e

# 1. Point Docker to Minikube’s daemon
echo "🔧 Configuring Docker to use Minikube..."
eval $(minikube docker-env)

# 2. Build your service images
echo "📦 Building backend image..."
docker build -t traceassist-backend:latest backend/
echo "📦 Building AI-Agent image..."
docker build -t traceassist-ai-agent:latest ai-agent/
echo "📦 Building frontend image..."
docker build -t traceassist-frontend:latest frontend/

# 3. Create namespaces
echo "📂 Ensuring namespaces exist..."
kubectl create namespace signoz     --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace traceassist --dry-run=client -o yaml | kubectl apply -f -

# 4. Install SigNoz via Helm
echo "🚀 Installing SigNoz..."
helm repo add signoz https://charts.signoz.io
helm repo update
helm upgrade --install signoz signoz/signoz \
  --namespace signoz \
  --wait --timeout=1h \
  -f k8s/signoz-values.yaml

# 5. Install cert-manager (for Operator webhook certificates)
echo "🔐 Installing cert-manager..."
kubectl apply --validate=false \
  -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml

echo "⏳ Waiting for cert-manager webhook..."
kubectl -n cert-manager rollout status deployment cert-manager-webhook --timeout=2m

# 6. Install the OpenTelemetry Operator (with CRDs & webhook)
echo "🔧 Installing OpenTelemetry Operator..."
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm repo update
helm upgrade --install opentelemetry-operator open-telemetry/opentelemetry-operator \
  --namespace opentelemetry-operator-system --create-namespace \
  --set installCRDs=true \
  --set webhook.certManager.enabled=true \
  --set webhook.autoGenerateCert=true

echo "⏳ Waiting for Operator to be ready..."
kubectl -n opentelemetry-operator-system rollout status deployment/opentelemetry-operator-controller-manager --timeout=2m

# 7. Apply your Collector & Instrumentation CRs
echo "📡 Deploying OpenTelemetryCollector & Instrumentation..."
kubectl apply -f k8s/otel-collector.yaml
kubectl apply -f k8s/instrumentation.yaml

# 8. Deploy your TraceAssist services
echo "🚀 Deploying TraceAssist services..."
kubectl apply -n traceassist \
  -f k8s/backend-deployment.yaml \
  -f k8s/backend-service.yaml \
  -f k8s/ai-agent-deployment.yaml \
  -f k8s/ai-agent-service.yaml \
  -f k8s/frontend-deployment.yaml \
  -f k8s/frontend-service.yaml

echo
echo "✅ All deployed!"
echo
echo "👉 To access your TraceAssist UI:"
echo "   kubectl -n traceassist port-forward svc/traceassist-frontend 5173:5173"
echo "   open http://localhost:5173"
echo
echo "👉 To access the SigNoz observability dashboard:"
echo "   kubectl -n signoz port-forward svc/signoz 8080:8080"
echo "   open http://localhost:8080"
