export default function GrafanaPanel() {
  return (
    <div className="bg-white p-4 rounded shadow">
      <h2 className="text-xl font-semibold mb-2">Grafana Dashboard</h2>
      <iframe
        src="http://localhost:3000"
        width="100%"
        height="600"
        frameBorder="0"
        title="Grafana"
      />
    </div>
  );
}