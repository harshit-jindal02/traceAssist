import React, { useState } from 'react';
import axios from 'axios';
import UploadForm from './components/UploadForm';
import SuggestionsPanel from './components/SuggestionsPanel';
import GrafanaPanel from './components/GrafanaPanel';
import { Box, Typography, Button, Divider, List, ListItem, ListItemIcon, ListItemText } from '@mui/material';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';

function App() {
  const [appId, setAppId] = useState(null);
  const [instrumented, setInstrumented] = useState(false);

  const handleAppReady = (id) => {
    setAppId(id);
  };

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
    <Box
      height={'100vh'}
      width={'100vw'}
      display={'flex'}
      sx={{
        background: 'linear-gradient(135deg, #232b5d 0%, #3e6b89 40%, #4fd1c5 100%)',
      }}
    >
      {/* Sidebar */}
      <Box
        width={'19%'}
        display={'flex'}
        flexDirection={'column'}
        pt={'3rem'}
        sx={{
          background: 'linear-gradient(135deg, #232b5d 0%, #3e6b89 100%)',
          boxShadow: 3
        }}
      >
        {/* Logo */}
        <Box
          sx={{
            mb: 3,
            display: 'flex',
            alignItems: 'center',
            flexDirection: 'column',
          }}
        >
          {/* Inline SVG logo placeholder */}
          <Box sx={{ mb: 1 }}>
            <svg width="125" height="125" viewBox="0 0 48 48" fill="none">
              <circle cx="24" cy="24" r="22" fill="#4fd1c5" stroke="#fff" strokeWidth="3" />
              <path d="M24 14v10l7 7" stroke="#232b5d" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
              <circle cx="24" cy="24" r="4" fill="#fff" stroke="#232b5d" strokeWidth="2" />
            </svg>
          </Box>
          <Typography
            variant="h6"
            color="#fff"
            fontWeight={700}
            letterSpacing={1}
            sx={{ mb: 0.5 }}
          >
            Trace Assist
          </Typography>
          <Typography
            variant="caption"
            color="#b0bec5"
            align="center"
            sx={{ px: 1 }}
          >
            AI-Powered Observability
          </Typography>
        </Box>
        <Divider sx={{ width: '100%', mb: 2, bgcolor: '#4fd1c5' }} />        
      </Box>

      {/* Main Content */}
      <Box
        width={'81vw'}
        flex={1}
        display="flex"
        alignItems="center"
        justifyContent="center"
        height={'100vh'}
      >
        <Box
          sx={{
            borderRadius: 5,
            p: 4,
            background: 'rgba(255,255,255,0.97)',
            boxShadow: '0 8px 32px rgba(44, 62, 80, 0.13)',
            backdropFilter: 'blur(6px)',
            width: appId ? '90%' : '700'
          }}
        >
          <Typography
            variant="h3"
            fontWeight={700}
            gutterBottom
            sx={{
              background: 'linear-gradient(90deg, #232b5d 0%, #4fd1c5 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              mb: 2,
            }}
          >
            Trace Assist Dashboard
          </Typography>
          <Typography
            variant="subtitle1"
            color="text.secondary"
            sx={{ mb: 3 }}
          >
            Accelerate observability with automated, AI-powered instrumentation for your applications.
          </Typography>

          {!appId && (
            <UploadForm onAppReady={handleAppReady} />
          )}

          {appId && !instrumented && (
            <Button
              variant="contained"
              size="large"
              startIcon={<AutoAwesomeIcon />}
              sx={{
                mt: 4,
                background: 'linear-gradient(90deg, #232b5d 0%, #4fd1c5 100%)',
                color: '#fff',
                fontWeight: 600,
                letterSpacing: 1,
                px: 4,
                py: 1.5,
                borderRadius: 3,
                boxShadow: '0 4px 16px rgba(44, 62, 80, 0.10)',
                textTransform: 'none',
                fontSize: '1.15rem',
                '&:hover': {
                  background: 'linear-gradient(90deg, #1e224d 0%, #3e6b89 100%)',
                },
              }}
              onClick={handleInstrumentAndRun}
            >
              Instrument & Run
            </Button>
          )}

          {instrumented && (
            <>
              <Box>
                <SuggestionsPanel appId={appId} />
              </Box>
              <Box mt={2}>
                <GrafanaPanel dashboardUid="YOUR_DASHBOARD_UID" />
              </Box>
            </>
          )}

        </Box>
      </Box>
    </Box>
  );
}

export default App;