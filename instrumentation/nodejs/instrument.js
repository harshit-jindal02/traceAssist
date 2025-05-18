const { execSync } = require("child_process");

function installDeps() {
  execSync("npm install --save @opentelemetry/api @opentelemetry/sdk-node @opentelemetry/auto-instrumentations-node", { stdio: "inherit" });
}

function wrapApp(entry) {
  const wrapper = `
const { NodeSDK } = require('@opentelemetry/sdk-node');
const { getNodeAutoInstrumentations } = require('@opentelemetry/auto-instrumentations-node');
const sdk = new NodeSDK({
  traceExporter: new (require('@opentelemetry/exporter-trace-otlp-grpc').OTLPTraceExporter)({
    url: 'http://otel-collector:4317',
  }),
  instrumentations: [getNodeAutoInstrumentations()],
});
sdk.start()
  .then(() => require('./${entry}'))
  .catch(err => console.error(err));
`;

  require("fs").writeFileSync("otel-wrapper.js", wrapper);
  console.log("Instrumentation added. Run using: node otel-wrapper.js");
}

const entry = process.argv[2] || "app.js";
installDeps();
wrapApp(entry);
