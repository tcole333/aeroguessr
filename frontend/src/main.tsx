import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { enableMapSet } from 'immer';
import 'leaflet/dist/leaflet.css';
import './index.css';
import App from './App.tsx';
import { initializeLogging } from './utils/logger';

// Initialize frontend logging
initializeLogging();

// Enable Immer MapSet plugin to work with Set objects
enableMapSet();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
