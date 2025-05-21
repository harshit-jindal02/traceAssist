import { Box, Typography } from '@mui/material';

export default function GrafanaPanel({ dashboardUid }) {
  return (
    <Box height={'70vh'}>
      <Typography variant='h4'>Grafana Dashboard</Typography>
      <iframe
        src={`http://localhost:3000/d/${dashboardUid}?orgId=1&kiosk`}
        width="100%"
        height="95%"
        frameBorder="0"
        title="Grafana Dashboard"
      />
    </Box>
  );
}
