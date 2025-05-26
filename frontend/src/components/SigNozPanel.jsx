import React from 'react';

export default function SigNozPanel({ appId }) {
  const src = `http://localhost:8080/applications?service=user-app-${appId}`;
  return (
    <iframe
      src={src}
      style={{ width: '100%', height: '600px', border: 0 }}
      title="SigNoz Dashboard"
    />
  );
}
