# Frontend

[docs/architecture.md](../docs/architecture.md#frontend) covers the store slices, the WebSocket client, URLs and persisted state. Scripts are in `package.json`.

- **Generated types** (`types/api.ts`, `types/ws.ts`): run the backend's `make openapi && make ws-schema` first, then `npm run gen:schema`. Running `gen:schema` alone rebuilds from stale YAML and silently drops fields from the zod schemas.
- **Plane deltas carry `route_hint`, never airports.** Derive what to show with `src/features/planes/routeDisplay.ts` (answer secrecy, PRD §5.2).
- **No location in the code.** The map's centre, monitored airport, basemap style and credits come from the client config (`GET /api/v0/config`, the `config` slice), so one build works anywhere.
- **API and WebSocket URLs are same-origin**: nginx serves them in production; under `npm run dev`, Vite proxies `/api` (with WebSocket upgrade) to the API on port `DEV_API_PORT` (8000 by default; `make demo` picks a free one). One build works on any host, so keep production hostnames out of the code.
- **The production image's nginx** (`nginx/default.conf.template`) serves the build and also proxies `/api/`, `/healthz` and `/readyz` to `BACKEND_URL`. Self-hosters rely on it, so keep it working (docs/self-hosting.md).
- **Tests sit next to the code** or in `__tests__/` folders (`*.test.ts(x)`), using Vitest, Testing Library and MSW. Run `npm run test:ci`, `npm run typecheck` and `npm run lint` before a PR.
- **Phase 3 rebuilds this UI:** map-first layout, evolved departure-board look (#176). Keep changes to the current layout small.
