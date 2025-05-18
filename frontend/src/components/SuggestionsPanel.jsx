import { useEffect, useState } from 'react';
import axios from 'axios';

export default function SuggestionsPanel() {
  const [suggestions, setSuggestions] = useState([]);

  useEffect(() => {
    async function fetchSuggestions() {
      const res = await axios.get('http://localhost:8000/suggestions');
      setSuggestions(res.data.suggestions || []);
    }
    fetchSuggestions();
  }, []);

  const handleAction = async (id, action) => {
    await axios.post(`http://localhost:8000/suggestions/${id}/${action}`);
    alert(`Suggestion ${action}ed`);
  };

  return (
    <div className="bg-white p-4 rounded shadow mb-6">
      <h2 className="text-xl font-semibold mb-2">AI Suggestions</h2>
      {suggestions.length === 0 && <p>No suggestions available.</p>}
      {suggestions.map((sug, idx) => (
        <div key={idx} className="border p-3 rounded mb-2">
          <p>{sug.text}</p>
          <div className="mt-2">
            <button
              onClick={() => handleAction(sug.id, 'accept')}
              className="bg-green-600 text-white px-3 py-1 rounded mr-2"
            >
              Accept
            </button>
            <button
              onClick={() => handleAction(sug.id, 'reject')}
              className="bg-red-600 text-white px-3 py-1 rounded"
            >
              Reject
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}