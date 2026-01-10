# Frontend Development Guide

React frontend for the Plane Guessing Game with real-time map visualization and WebSocket state synchronization.

## Stack

- **Framework**: React 18 with TypeScript
- **Build**: Vite
- **State**: Zustand with slices
- **Styling**: Tailwind CSS
- **Map**: Leaflet + React Leaflet
- **Testing**: Vitest + Testing Library

## Project Structure

```
frontend/src/
├── components/
│   ├── Map/
│   │   ├── GameMap.tsx      # Main map container
│   │   ├── PlaneMarker.tsx  # Individual plane
│   │   └── PlaneTrail.tsx   # Flight trail polyline
│   ├── Panel/
│   │   ├── PlanesTab.tsx    # Plane list
│   │   ├── LeaderboardTab.tsx
│   │   └── SettingsTab.tsx
│   └── ui/                  # Shared UI components
├── features/
│   ├── game/
│   │   ├── gameSlice.ts     # Game state slice
│   │   └── components/      # Game-specific UI
│   └── connection/
│       └── connectionSlice.ts
├── store/
│   └── createRootStore.tsx  # Zustand root store
├── hooks/
│   ├── useWebSocketManager.ts
│   └── useAutoRejoin.ts
├── lib/
│   └── websocket.ts         # WS client
└── types/
    ├── api.ts               # Generated from OpenAPI
    └── ws.ts                # Generated from WS schema
```

## State Management

### Zustand Store Structure

```typescript
interface RootState {
  // Connection slice
  wsStatus: "disconnected" | "connecting" | "connected";
  roomCode: string | null;
  nickname: string | null;

  // Game slice
  players: Record<string, Player>;
  currentRound: RoundData | null;
  isHost: boolean;

  // Planes slice
  planes: Record<string, PlaneState>;
  selectedPlaneHex: string | null;

  // UI slice
  darkMode: boolean;
  panelTab: "planes" | "leaderboard" | "settings";
}
```

### Slice Pattern

```typescript
// features/game/gameSlice.ts
export const createGameSlice: StateCreator<GameSlice> = (set, get) => ({
  players: {},
  addPlayer: (player) =>
    set((state) => ({
      players: { ...state.players, [player.nickname]: player },
    })),
});
```

## WebSocket Integration

### Message Handling

```typescript
// hooks/useWebSocketManager.ts
useEffect(() => {
  ws.onMessage("delta", (payload) => {
    if (payload.planes?.updated) {
      updatePlanes(payload.planes.updated);
    }
    if (payload.scores) {
      updateScores(payload.scores);
    }
  });
}, []);
```

### Type Safety

Types are auto-generated from backend schemas:

```bash
make openapi    # → types/api.ts
make ws-schema  # → types/ws.ts
```

## Component Patterns

### Mobile-First

```tsx
// Responsive panels
<div className="
  fixed bottom-0 left-0 right-0 h-1/3
  md:left-0 md:top-0 md:bottom-0 md:w-80 md:h-full
">
```

### Map Integration

```tsx
<MapContainer center={[lat, lon]} zoom={10}>
  <TileLayer url="..." />
  {planes.map((plane) => (
    <PlaneMarker key={plane.hex_ident} plane={plane} />
  ))}
</MapContainer>
```

### React Portal for Modals

```tsx
// Ensure z-index above map
createPortal(<RoundResultModal />, document.body);
```

## Testing

```bash
# Run all tests
npm run test:ci

# Watch mode
npm run test

# Specific file
npm run test -- PlaneMarker.test.tsx

# Coverage
npm run test:coverage
```

### Testing Patterns

```typescript
// Use Testing Library
render(<PlaneMarker plane={mockPlane} />);
expect(screen.getByRole('img')).toHaveAttribute('alt', 'UAL123');

// Mock Zustand store
const mockStore = createMockStore({ planes: { 'abc123': mockPlane } });
```

## Common Tasks

```bash
# Development server
npm run dev

# Network-accessible dev
npm run dev -- --host

# Production build
npm run build

# Type check
npm run typecheck

# Lint
npm run lint
```

## Key Files

| File                           | Purpose                                  |
| ------------------------------ | ---------------------------------------- |
| `hooks/useWebSocketManager.ts` | WebSocket lifecycle & message handling   |
| `store/createRootStore.tsx`    | Zustand store with all slices            |
| `components/Map/GameMap.tsx`   | Main map with planes                     |
| `features/game/gameSlice.ts`   | Game state (players, rounds)             |
| `lib/websocket.ts`             | WebSocket client class                   |
| `assets/airports.json`         | Airport autocomplete data (~3K airports) |

## Environment Variables

Set in `.env` or at build time:

| Variable       | Default                 | Description        |
| -------------- | ----------------------- | ------------------ |
| `VITE_WS_URL`  | `ws://localhost:8000`   | WebSocket endpoint |
| `VITE_API_URL` | `http://localhost:8000` | REST API endpoint  |
