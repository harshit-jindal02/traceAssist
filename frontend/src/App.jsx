import UploadForm from './components/UploadForm';
import SuggestionsPanel from './components/SuggestionsPanel';
import GrafanaPanel from './components/GrafanaPanel';

export default function App() {
  return (
    <div className="min-h-screen bg-gray-100 p-6">
      <h1 className="text-3xl font-bold mb-6">Auto Instrumentation Dashboard</h1>
      <UploadForm />
      <SuggestionsPanel />
      <GrafanaPanel />
    </div>
  );
}