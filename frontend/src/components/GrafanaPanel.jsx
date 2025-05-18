import React from 'react';

export default function GrafanaPanel({ dashboardUid }) {
  return (
    <div className="mb-12">
      <h2 className="text-2xl font-semibold mb-2">Grafana Dashboard</h2>
      <iframe
        src={`http://localhost:3000/d/${dashboardUid}?orgId=1&kiosk`}
        width="100%"
        height="600"
        frameBorder="0"
        title="Grafana Dashboard"
      />
    </div>
  );
}
