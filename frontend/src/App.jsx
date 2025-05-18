// /frontend/src/App.jsx
import React, { useState } from 'react';
import axios from 'axios';
import UploadForm from './components/UploadForm';
import SuggestionsPanel from './components/SuggestionsPanel';
import GrafanaPanel from './components/GrafanaPanel';

function App() {
  const [appId, setAppId] = useState(null);
  const [instrumented, setInstrumented] = useState(false);

  // Called by UploadForm when /upload or /clone returns an app_id
  const handleAppReady = (id) => {
    setAppId(id);
  };

  // Runs /instrument then /run
  const handleInstrumentAndRun = async () => {
    try {
      await axios.post(
        'http://localhost:8000/instrument',
        { app_id: appId },
        { headers: { 'Content-Type': 'application/json' } }
      );
      setInstrumented(true);
      await axios.post(
        'http://localhost:8000/run',
        { app_id: appId },
        { headers: { 'Content-Type': 'application/json' } }
      );
    } catch (err) {
      console.error(err.response?.data || err.message);
      alert('Failed to instrument or run the application. Check console for details.');
    }
  };

  return (
    <div className="container mx-auto p-6">
      <h1 className="text-3xl font-bold mb-6">Auto Instrumentation Dashboard</h1>

      {!appId && (
        <UploadForm onAppReady={handleAppReady} />
      )}

      {appId && !instrumented && (
        <button
          onClick={handleInstrumentAndRun}
          className="bg-blue-600 text-white px-4 py-2 rounded mb-6"
        >
          Instrument & Run
        </button>
      )}

      {instrumented && (
        <>
          <SuggestionsPanel appId={appId} />

          <GrafanaPanel
            // Replace with the UID of a dashboard you've created/imported in Grafana
            dashboardUid="YOUR_DASHBOARD_UID"
          />
        </>
      )}
    </div>
  );
}

export default App;
