// frontend/src/components/SuggestionsPanel.jsx
import React, { useState, useEffect } from 'react';
import { Box, Typography, CircularProgress } from '@mui/material';
import axios from 'axios';

export default function SuggestionsPanel({ apiBase, appId }) {
  const [suggestions, setSuggestions] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchSuggestions = async () => {
      setLoading(true);
      try {
        const res = await axios.post(
          `${apiBase}/suggestions`,
          { app_id: appId },
          { headers: { 'Content-Type': 'application/json' } }
        );
        setSuggestions(res.data.suggestions || '');
      } catch (err) {
        console.error('Error fetching suggestions:', err.response?.data || err.message);
        alert('Failed to fetch AI suggestions. Check console.');
      } finally {
        setLoading(false);
      }
    };

    if (appId) {
      fetchSuggestions();
    }
  }, [apiBase, appId]);

  if (loading) {
    return (
      <Box textAlign="center" my={2}>
        <CircularProgress />
        <Typography>Loading AI suggestions…</Typography>
      </Box>
    );
  }

  return (
    <Box my={2}>
      <Typography variant="h4" gutterBottom>
        AI Suggestions
      </Typography>
      {suggestions ? (
        <Typography component="pre" sx={{ whiteSpace: 'pre-wrap' }}>
          {suggestions}
        </Typography>
      ) : (
        <Typography>No suggestions available.</Typography>
      )}
    </Box>
  );
}
