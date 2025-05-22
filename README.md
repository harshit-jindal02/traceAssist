
# 🚀 TraceAssist

**TraceAssist** is a Kubernetes-native observability helper that lets developers automatically instrument, analyze, and visualize their applications. Developers can upload a ZIP of their code or provide a repo link; TraceAssist will deploy the app in-cluster, auto-instrument it with OpenTelemetry, and surface AI-powered suggestions. Metrics, logs, and traces are displayed in a SigNoz dashboard embedded in the UI.

---

## 🚀 Features

* **Zero-touch instrumentation** via the OpenTelemetry Operator
* **AI-driven suggestions** for improving observability (built with OpenAI)
* **Single-pane observability** using SigNoz (replaces Prometheus, Jaeger, Grafana, Loki)
* **Kubernetes-native**: runs entirely in Minikube (or any K8s cluster)
* **One-click deploy** with `run.sh` and tear-down with `cleanup.sh`

---

## 📋 Prerequisites

* [Minikube](https://minikube.sigs.k8s.io/docs/) (v1.30+)
* [kubectl](https://kubernetes.io/docs/tasks/tools/)
* [Helm](https://helm.sh/docs/helm/helm_install/)
* Docker (for building images into Minikube)
* [OpenAI API key](https://platform.openai.com/account/api-keys)
* `backend/.env` and `ai-agent/.env` files containing at least:

  ```dotenv
  OPENAI_API_KEY=sk-...
  ```

---

## 🛠 Setup & Deployment

1. **Clone the repo**

   ```bash
   git clone https://github.com/harshit-jindal02/traceAssist.git
   cd traceAssist
   ```

2. **Start Minikube**

   ```bash
   minikube start --cpus=4 --memory=8192
   eval $(minikube docker-env)
   ```

3. **Prepare environment Secrets**

   ```bash
   kubectl create namespace traceassist || true
   kubectl -n traceassist create secret generic backend-secret --from-env-file=backend/.env
   kubectl -n traceassist create secret generic ai-agent-secret --from-env-file=ai-agent/.env
   ```

4. **Deploy everything**

   ```bash
   chmod +x run.sh
   ./run.sh
   ```

   This will:

   * Build and load Docker images into Minikube
   * Install SigNoz via Helm
   * Install cert-manager and the OpenTelemetry Operator (with CRDs)
   * Apply your OpenTelemetryCollector and Instrumentation CRDs
   * Deploy the `backend`, `ai-agent`, and `frontend` services in the `traceassist` namespace

---

## 🔍 Accessing the UIs

* **TraceAssist UI** (frontend):

  ```bash
  kubectl -n traceassist port-forward svc/traceassist-frontend 5173:5173
  # Open http://localhost:5173
  ```

* **Observability dashboard** (SigNoz):

  ```bash
  kubectl -n signoz port-forward svc/signoz 8080:8080
  # Open http://localhost:8080
  ```

In the TraceAssist UI you can upload ZIPs or clone repos, trigger auto-instrumentation, run the app, and view AI suggestions.

---

## 🧹 Cleanup

To tear down everything:

```bash
chmod +x cleanup.sh
./cleanup.sh
```

This will uninstall SigNoz and delete the `traceassist` namespace.

---

## 📝 Troubleshooting

* **Pods Pending**: Ensure images are built into Minikube (`eval $(minikube docker-env)` runs in your shell before `run.sh`).
* **ImagePullBackOff**: Check `imagePullPolicy: Never` is set in each deployment YAML.
* **Operator webhook errors**: Verify cert-manager is running in `cert-manager` namespace.
* **Missing OPENAI\_API\_KEY**: Confirm `.env` files are populated and Secrets are created.