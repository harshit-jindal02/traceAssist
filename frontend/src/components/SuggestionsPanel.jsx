import React, { useState, useEffect } from 'react';
import axios from 'axios';

export default function SuggestionsPanel({ appId }) {
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchSuggestions = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`http://localhost:8000/suggestions?app_id=${encodeURIComponent(appId)}`);
      setSuggestions(res.data.suggestions || []);
    } catch (err) {
      console.error('Error fetching suggestions:', err.response?.data || err.message);
      alert('Failed to fetch AI suggestions. Check console.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (appId) {
      fetchSuggestions();
    }
  }, [appId]);

  if (loading) return <p>Loading AI suggestions…</p>;

  return (
    <div className="mb-8">
      <h2 className="text-2xl font-semibold mb-2">AI Suggestions</h2>
      {suggestions.length > 0
        ? suggestions.map((s, i) => <p key={i} className="mb-1">• {s}</p>)
        : <p>No suggestions available.</p>
      }
    </div>
  );
}
