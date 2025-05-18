# Front-End Development Standards & Guidelines for LLM Agents

> **Scope**
> These conventions apply to all code under `frontend/` and are written so that an autonomous LLM agent can generate production-ready React/TypeScript code that satisfies the Plane Guessing Game PRD and passes CI (_pre-commit_, unit, integration, and accessibility tests).

---

## 1 Project Stack Summary

- **Framework:** React 18 (function components with hooks)
- **Bundler:** Vite 5 (ESM, HMR)
- **Language:** TypeScript 5 – `strict` mode **ON**
- **State:** Zustand (vanilla store + Immer)
- **Styling:** Tailwind CSS 3 + Prettier plugin
- **Mapping:** React-Leaflet 4 + Leaflet 1.9
- **Testing:**
  - Unit – Vitest + React Testing Library (RTL)
  - Integration (WS) – Vitest + `msw`
  - E2E – Cypress 12 (run in CI only)
- **Lint / Format:** ESLint (airbnb-custom) + Ruff (\*.py only) + Prettier
- **Build Output:** `frontend/dist/` – served by Nginx in Docker image.

---

## 2 File/Folder Conventions

| Folder                     | Purpose                                            |
| -------------------------- | -------------------------------------------------- |
| `frontend/src/components/` | Dumb/presentational components (no external state) |
| `frontend/src/features/`   | Feature folders (slice store + UI + tests)         |
| `frontend/src/hooks/`      | Re-usable hooks (`useWebSocket`, `useDebounce` …)  |
| `frontend/src/lib/`        | One-off helpers (e.g. distance calc)               |
| `frontend/src/assets/`     | Plane SVGs, static JSON (airports list)            |
| `frontend/types/`          | Generated types from OpenAPI & WS schema           |
| `frontend/__tests__/`      | Cross-feature integration tests                    |

**Naming rules**

- Files: `PlaneList.tsx`, `usePlaneStore.ts` (Pascal for components, camel for hooks).
- Test files sit next to source: `Whatever.test.tsx`.
- CSS modules **not** used – Tailwind handles styling.

---

## 3 Type Safety & Generated Schemas

1. **Autogen types**: run `pnpm gen:schema` to fetch `docs/ws_schema.yaml` & `docs/api_openapi.yaml` and emit:
   - `types/ws.ts` – with Zod schemas + TypeScript types
   - `types/api.ts` – with OpenAPI-typed clients via `openapi-typescript`
2. **Runtime validation**: Every inbound WS message **must** be parsed with the matching Zod schema before updating state. Invalid messages ➜ console error + ignored.
3. **No `any`**: Disallow `any` in `tsconfig.json` (CI will fail).

---

## 4 WebSocket Client Contract

Create a singleton `WebSocketClient` that:

```ts
class WebSocketClient {
  connect(roomCode: string, nickname: string): void;
  send<T extends OutboundMsg>(msg: T): void;
  subscribe(cb: (msg: InboundMsg) => void): UnsubscribeFn;
}
```

- Auto-reconnect with back-off 0.5→4 s (see PRD §5.4).
- Heartbeat: send `ping` every 10 s; if 3 missed **`pong`** ➜ mark disconnected.
- Queue outbound msgs while disconnected.
- Uses message envelopes `{type, payload, ts}`.
- Exposed via React context (`<ConnectionProvider>`).

---

## 5 State Management (Zustand)

Organise stores as **slices** combined with `createStore`:

```ts
export interface RootState {
  connection: ConnectionSlice;
  planes: PlaneSlice;
  game: GameSlice;
  ui: UiSlice;
}
```

- Each slice lives in its feature folder and exports selectors.
- Use Immer middleware for immutable updates.
- Persist only `ui` (night mode) in `localStorage`.

---

## 6 UI/UX Principles

1. **Mobile-first** (portrait). ≥600 px ➜ panel docks left.
2. **Accessibility**: All interactive elements – keyboard navigable, `aria-*` labels. Colour-blind safe palette.
3. **Performance**: Map renders ≤300 ms per update. Use React.memo on plane markers.
4. **Styling**: Tailwind class composition only. Shared design tokens in `tailwind.config.js`.
5. **Animations**: Use Framer Motion for confetti & panel transitions.

---

## 7 Testing Strategy

| Layer            | Tools          | Requirement                                      |
| ---------------- | -------------- | ------------------------------------------------ |
| Unit             | Vitest, RTL    | >90 % statements; each component + util          |
| Integration (WS) | Vitest + `msw` | Simulate WS server incl. ping/pong               |
| E2E              | Cypress        | Room creation→5-round flow on viewport iPhone 12 |
| a11y             | `jest-axe`     | No viols on main views                           |

CI job `pnpm test:ci` must pass with coverage thresholds.

---

## 8 Logging & Error Handling

- Use [`debug`](https://www.npmjs.com/package/debug) namespaced logs (`plane:ws`, `plane:state`, `plane:ui`).
- Show user-friendly toast via [Sonner](https://sonner.emilkowal.ski/) on non-fatal errors.
- Fatal WS errors ➜ retry popup with reconnect button.

---

## 9 Developer Workflow

1. `pre-commit` hooks: ESLint, Prettier, type-check, Vitest.
2. Commit messages – Conventional Commits (`feat(frontend): …`).
3. New components ➜ Storybook story; visual diff tested with Chromatic.
4. If code adds TODO/FIXME ➜ update `TECH_DEBT.md`.
5. Doc changes in API/WS ➜ regenerate schema (`make openapi`) and commit.

---

## 10 Making Backend Requests

If the frontend uncovers missing backend features or schema mismatches:

1. Append a **single Markdown bullet** to `frontend/backend_requests.md` using this template:
   ```md
   ### [YYYY-MM-DD] Short title

   **Context:** What failed / is missing.
   **Proposed change:** REST/WS contract update (be explicit).
   **Priority:** High / Medium / Low
   ```
2. **Create a GitHub issue** referencing the bullet so backend work can be prioritised.
3. **Do _not_ modify or add any code inside the `backend/` folder.** Front-end contributors must treat the backend as **read-only**; all contract changes flow through `frontend/backend_requests.md`.
4. Do **not** block frontend work; stub with mock data and continue. Any mock data should be placed behind an env variable called MOCK_DATA that when set to true allows the use of mock data, when false will not use any.

---

## 11 Accessibility Checklist (WCAG 2.1 AA)

- Semantic HTML tags (\<button\>, \<nav\>, etc.)
- Colour contrast ≥4.5:1
- Focus outline visible
- Touch targets ≥44 px
- `aria-live` for score updates

---

## 12 Task Tracker

> Use this checklist to track front-end MVP progress. Check a box when its sub-tasks are complete **and** merged in `main`.

- [ ] **Tooling bootstrap**
  - [x] Scaffold Vite + React + TS strict (`pnpm create vite`)
  - [x] Install ESLint, Prettier, Tailwind, Vitest, RTL, msw, Cypress, Storybook
  - [x] Add `pnpm gen:schema` script to autogenerate API/WS types
  - [x] Update .pre-commit-config.yaml with front end hooks
- [x] **Core infrastructure**
  - [x] Implement `WebSocketClient` with reconnect & heartbeat
  - [x] Create Zustand root store with empty slices
  - [x] Unit tests for reconnect & message validation
- [ ] **State slices**
  - [x] `connection` slice
  - [x] `planes` slice
  - [x] `game` slice
  - [x] `ui` slice (persist night-mode)
- [x] **Autogenerated types & validation**
  - [x] Zod schemas from `ws_schema.yaml`
  - [x] OpenAPI client generation
  - [x] Helper `assertWsMessage` + tests
- [ ] **Base layout**
  - [ ] `AppShell` with MapView & SlidingPanel
  - [ ] Responsive docking behaviour
- [ ] **Map & plane rendering**
  - [ ] Integrate React-Leaflet map centred on Boston
  - [ ] Plane markers + fading trails
  - [ ] Performance benchmark ≤300 ms update
- [ ] **Panel tabs UI**
  - [ ] Planes list panel
  - [ ] Leaderboard with confetti
  - [ ] Settings panel with basic host controls
- [ ] **Game flow handling**
  - [ ] Join / create room screens (REST)
  - [ ] Handle all WS inbound message types
  - [ ] Guess form & submission
  - [ ] Host controls (`selectPlane`, `startRound`, `skipRound` once available)
- [ ] **Accessibility pass** (WCAG 2.1 AA)
- [ ] **End-to-end Cypress tests** for 5-round flow
- [ ] **Storybook & visual regression** setup
- [ ] **Documentation updates** (README, Tech Debt)

_End of guidelines_
