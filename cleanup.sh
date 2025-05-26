#!/usr/bin/env bash
set -e

echo "🛑 Stopping any lingering port‐forwards…"
pkill -f "kubectl port-forward.*traceassist-frontend" 2>/dev/null || true
pkill -f "kubectl port-forward.*signoz-frontend"      2>/dev/null || true

echo "🔥 Deleting Kubernetes workloads and config…"
kubectl delete daemonset traceassist-collector          -n traceassist --ignore-not-found
kubectl delete deployment traceassist-backend traceassist-ai-agent traceassist-frontend \
                                                       -n traceassist --ignore-not-found
kubectl delete svc        traceassist-backend traceassist-ai-agent traceassist-frontend \
                                                       -n traceassist --ignore-not-found
kubectl delete secret     backend-secret ai-agent-secret        -n traceassist --ignore-not-found
kubectl delete serviceaccount traceassist-sa                             -n traceassist --ignore-not-found
kubectl delete -f k8s/instrumentation.yaml               --ignore-not-found

echo "🏷️  Deleting namespaces…"
# --wait=false returns immediately instead of blocking until full removal
kubectl delete namespace traceassist signoz cert-manager opentelemetry-operator-system \
  --ignore-not-found --wait=false

echo "🗑️  Deleting any remaining OTel custom resources…"
kubectl delete instrumentations.instrumentation.opentelemetry.io \
   --all --all-namespaces --ignore-not-found || true
 kubectl delete opentelemetrycollectors.opentelemetry.io \
   --all --all-namespaces --ignore-not-found || true

echo "🔨 Removing CRDs…"
kubectl delete crd \
  challenges.acme.cert-manager.io \
  certificaterequests.cert-manager.io \
  issuers.cert-manager.io \
  certificates.cert-manager.io \
  orders.acme.cert-manager.io \
  instrumentations.instrumentation.opentelemetry.io \
  opentelemetrycollectors.opentelemetry.io \
  --ignore-not-found

echo "📦 Uninstalling Helm releases…"
helm uninstall signoz                 -n signoz                 || true
helm uninstall opentelemetry-operator -n opentelemetry-operator-system || true
helm uninstall cert-manager           -n cert-manager           || true

echo "🐳 Cleaning up Docker images in Minikube…"
eval "$(minikube docker-env)"
docker rmi -f traceassist-backend:latest traceassist-ai-agent:latest traceassist-frontend:latest || true
docker images | awk '/^user-app-/{print $1":"$2}' | xargs -r docker rmi -f       || true
docker rmi -f otel/opentelemetry-collector-contrib:0.119.0                      || true
eval "$(minikube docker-env -u)"

echo "🗑️  Removing local build directories…"
rm -rf ./k8s ./user-apps

echo "✅ All cleanup tasks complete."
