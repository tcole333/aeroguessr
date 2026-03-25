# Frontend

The frontend is a Vite + React + TypeScript application for AeroGuessr. It renders the live flight map, manages multiplayer room state through WebSockets, and provides the guessing UI for solo and room-based play.

## Commands

```bash
# from frontend/
npm install
npm run dev
npm run build
npm run test
npm run lint
```

## Architecture

- `src/lib/WebSocketClient.ts`: reconnecting WebSocket client with heartbeat support
- `src/hooks/useWebSocketManager.ts`: maps inbound server messages into Zustand actions
- `src/store/createRootStore.tsx`: root Zustand store composed from connection, planes, game, and UI slices
- `src/components/layout/AppShell.tsx`: page shell that combines the map, panels, and current game view
- `src/features/`: feature-oriented UI modules for rooms, map, game flow, planes, settings, and connection state

## Environment

The frontend uses standard Vite environment variables:

- `VITE_API_BASE_URL`: optional HTTP base URL for the backend API
- `VITE_WS_BASE_URL`: optional WebSocket base URL when the app is not served from the same origin as the API

When these variables are omitted, the frontend defaults to same-origin requests (`/api/v0` for HTTP and `window.location.origin` for WebSockets), which keeps production deploys portable.
