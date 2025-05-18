import os
import subprocess
import sys

def install_opentelemetry_deps():
    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "opentelemetry-distro", "opentelemetry-exporter-otlp"], check=True)

def instrument_python_app(entry_point: str):
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://otel-collector:4317"
    os.environ["OTEL_TRACES_EXPORTER"] = "otlp"
    os.environ["OTEL_METRICS_EXPORTER"] = "otlp"
    os.environ["OTEL_LOGS_EXPORTER"] = "otlp"
    
    print(f"Running with OpenTelemetry Instrumentation: {entry_point}")
    subprocess.run(["opentelemetry-instrument", "python", entry_point])

if __name__ == "__main__":
    app_entry = sys.argv[1] if len(sys.argv) > 1 else "app.py"
    install_opentelemetry_deps()
    instrument_python_app(app_entry)
