// Determine the API Base URL from the environment or use local default
export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Construct the WebSocket URL by replacing http with ws, handling https -> wss
export const WS_URL = API_BASE_URL.replace(/^http/, 'ws') + '/ws';
