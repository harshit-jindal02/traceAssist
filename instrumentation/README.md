# 📦 Instrumentation Scripts

These scripts enable auto-instrumentation for user applications in various languages.

| Language | Method |
|---------|--------|
| Python | Uses `opentelemetry-distro` CLI |
| Node.js | Injects wrapper code |
| Java | Uses OpenTelemetry agent |
| Go | Shows instructions (Go requires code-level instrumentation) |

Each script sets the OTLP endpoint as `http://otel-collector:4317`.

You can extend these scripts to inject config files, Docker overrides, etc.
