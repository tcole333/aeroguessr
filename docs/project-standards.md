# Project Coding & Documentation Standards

This document defines coding conventions, architectural patterns, and documentation requirements for the AeroGuessr codebase. For development workflow, see @CLAUDE.md.

## 1. Code Style & Conventions

### 1.1 Python (Backend)
```python
# Google-style docstrings required
def process_flight_data(icao: str, altitude: int) -> FlightData:
    """Process incoming flight data from ADS-B feed.

    Args:
        icao: ICAO 24-bit address (hex string)
        altitude: Altitude in feet

    Returns:
        Processed flight data object

    Raises:
        ValueError: If ICAO format is invalid
    """
```

**Requirements:**
- Type hints for all function parameters and returns
- Docstrings for all public functions/classes
- Keep functions short (about 50 lines) and extract helpers. `websocket_endpoint` in `backend/routes/rooms.py` is the known exception; the Phase 2 engine rebuild (#148) replaces it.
- Use `pydantic.BaseModel` for data structures
- Async functions for all routes and I/O operations
- No commented-out code: delete it. Ruff's ERA001 fails the check on it.
- Log important operations and errors

### 1.2 TypeScript/React (Frontend)
```typescript
// Functional components with typed props
interface FlightMapProps {
  flights: Flight[];
  center: LatLng;
  onFlightSelect: (flight: Flight) => void;
}

export const FlightMap: React.FC<FlightMapProps> = ({
  flights,
  center,
  onFlightSelect
}) => {
  // Component logic
};
```

**Requirements:**
- Functional components, except error boundaries (React requires a class)
- Full TypeScript types (no `any`)
- Props interfaces for all components
- Tailwind CSS for styling
- ESLint and Prettier compliance

### 1.3 Commit Messages
Use Conventional Commits:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation only
- `style:` Code style (formatting, etc)
- `refactor:` Code restructuring
- `test:` Test additions/changes
- `chore:` Build process, dependencies
- `perf:` Performance improvement
- `ci:` CI and release workflows

## 2. Architecture Patterns

### 2.1 Backend Structure
```
backend/
├── app.py              # FastAPI app initialization
├── routes/             # API endpoints & WebSocket handlers
├── services/           # Business logic layer
├── schemas/            # Pydantic models
├── ingest/             # ADS-B data ingestion
├── scripts/            # Utility scripts
└── utils/              # Shared utilities
```

### 2.2 Frontend Structure
```
frontend/
├── src/
│   ├── components/     # Shared React components
│   ├── features/       # Feature-based modules with slices
│   ├── pages/          # Page-level components
│   ├── hooks/          # Custom React hooks
│   ├── lib/            # Core libraries (WebSocket client)
│   ├── mocks/          # MSW mock handlers
│   ├── services/       # API client code
│   ├── store/          # Zustand root store with slices
│   └── assets/         # Static assets (icons, images)
├── types/              # Generated TypeScript types
│   ├── api.ts          # API types from OpenAPI
│   └── ws.ts           # WebSocket types from schema
```

**State Management Pattern:**
- Single root store (`createRootStore`) using Zustand
- Feature slices combined into root state (connection, game, planes, ui)
- Immer middleware for immutable updates
- Persist middleware for UI preferences

### 2.3 Testing Structure
- **Backend**: Unit tests mirror source structure: `tests/backend/routes/test_*.py`
- **Integration**: `tests/integration/`, against a real Redis and a live backend (see [tests/README.md](../tests/README.md))
- **Frontend**: Tests next to components or in `__tests__/` folders (`*.test.ts(x)`), using Vitest + Testing Library
- **Coverage**: backend 50% floor (CI); frontend 1% (`vitest.config.ts`)

## 3. Documentation Requirements

### 3.1 Code Documentation
- **Functions**: Document purpose, parameters, returns, exceptions
- **Complex Logic**: Inline comments explaining "why" not "what"
- **APIs**: OpenAPI annotations on all endpoints
- **Components**: JSDoc comments for props and behavior

### 3.2 Project Documentation
- **Long-lived docs**:
  - [README](../README.md), for players and self-hosters;
  - [CONTRIBUTING](../CONTRIBUTING.md), for the development setup, conventions and common tasks;
  - [PRD](PRD.md), for what the game does;
  - [architecture](architecture.md), for how it works;
  - [self-hosting](self-hosting.md), for running it on your own receiver;
  - [deployment](deployment.md), the aeroguessr.com runbook;
  - [tests/README](../tests/README.md);
  - [NOTICE](../NOTICE.md), for third-party credits and licenses.
  Each fact lives in one of them. Update that one and link to it from elsewhere, rather than restating the fact.
- **API or WebSocket changes**: regenerate the schemas and types (3.3) and commit them
- **Plans, status and findings** belong in GitHub issues and PRs, not in the repo. Use the templates for features, bugs and tech debt.

### 3.3 Type Generation
It takes two steps, in this order:
1. `make openapi && make ws-schema` writes `docs/api_openapi.yaml` and `docs/ws_schema.yaml` from the backend.
2. `cd frontend && npm run gen:schema` writes `frontend/types/api.ts` and `frontend/types/ws.ts` from that YAML.

Running step 2 alone rebuilds the types from whatever YAML is committed. If that YAML is stale, fields silently drop from the zod schemas.

CI runs both steps and fails if the output differs from what is committed.

## 4. Logging Standards

### 4.1 Backend Logging
```python
import logging

logger = logging.getLogger(__name__)

# Log levels by scenario
logger.debug(f"Processing flight {icao}")  # Detailed debugging
logger.info(f"New player joined: {player_id}")  # Normal operations
logger.warning(f"Rate limit approaching: {current}/{limit}")  # Warnings
logger.error(f"Failed to fetch flight data: {e}")  # Recoverable errors
logger.critical(f"Redis connection lost")  # System failures
```

### 4.2 Frontend Logging
```typescript
// Problems worth seeing in any browser console
console.warn('[VectorBaseLayer] Basemap error', String(event.error));
console.error('Failed to copy room code:', err);

// Diagnostics, shown only after localStorage.debug = 'plane:*'
import debug from 'debug';
const log = debug('plane:ws');
log('connected to', url);
```
- ESLint warns on `console.log` and `console.debug`, so a new one fails `npm run lint` at the warning cap.
- The browser's logs stay in the browser; nothing sends them to the backend.

### 4.3 Log Output
- **Backend logs**: `logs/backend.log`
- **Integration test logs**: `logs/integration.log`
- **Format**: API `%(asctime)s - %(name)s - %(levelname)s - %(message)s`; ingest `%(asctime)s %(levelname)s [service] %(name)s: %(message)s` (`backend/utils/logging_config.py`)

### 4.4 Log Rotation
- **Development Settings**:
  - Rotate when file size exceeds 5MB
  - Keep only 1 backup file
  - Python's RotatingFileHandler for the backend log
- **On the Pi**: Docker caps container output at 10 MB × 3, and the app rotates its own files. [deployment.md](deployment.md#logs) lists what bounds each log. `infra/logrotate.d/plane-game` exists but is not installed.

## 5. API & WebSocket Standards

### 5.1 REST API
- Version in URL: `/api/v0/`
- Resource-based naming: `/rooms`, `/players`
- Standard HTTP status codes
- Errors use FastAPI's format: `{"detail": "Error message"}`

### 5.2 WebSocket Messages
- Envelope `{type, payload, ts}`, with `ts` in epoch milliseconds
- Message types are camelCase (`selectPlane`, `roundResult`); payload fields are snake_case
- Errors are `{type: "error", payload: {code, message}}`
- Define messages as Pydantic models; `make ws-schema` generates `docs/ws_schema.yaml` from them

## 6. Environment & Configuration

### 6.1 Environment Variables
- Define every backend setting in `backend/settings.py`, with its default, and read it with `get_settings()`, never `os.getenv`.
- List it in `.env.example` with a description. `tests/backend/test_settings.py` enforces this.
- No secrets in code or commits. gitleaks checks staged changes in pre-commit, and the files and each pull request's commits in CI.

### 6.2 Feature Flags
- Use environment variables: `FAKE_ADSB=1`
- Document the behavior in `.env.example`, and in [self-hosting.md](self-hosting.md) when self-hosters need it
- Default to production behavior

## 7. Quality Checks

### 7.1 Pre-commit Hooks
All code must pass:
- Python: Ruff (linting + formatting)
- TypeScript: ESLint + Prettier
- JSON/YAML: syntax validation
- File size limits
- No merge conflicts
- Shell scripts: shellcheck
- GitHub workflows: actionlint, which also checks their `run:` scripts when `shellcheck` is on your PATH
- No secrets in staged changes: gitleaks

### 7.2 CI Requirements
`.github/workflows/ci.yml` runs on pushes to `main` and on every PR, whatever its base branch, so stacked PRs get CI too. Every job must be green:
- Ruff
- the other pre-commit hooks: file checks, shellcheck and actionlint
- gitleaks finds no secret in the files or in the pull request's commits
- the PR title is a conventional commit (1.3), because a squash merge uses it as the commit message (a single-commit PR uses its commit's message, which is checked too); a separate workflow, `pr-title.yml`, checks it
- skipped tests reference an issue (`scripts/check_test_skips.py`)
- backend unit tests (50% coverage floor)
- integration tests against real Redis
- frontend lint (capped warnings), typecheck and tests
- generated schemas and types match the code
- Docker image builds

CI is advisory: there is no branch protection, and the maintainer's Pi deploys whatever lands on `main`. Check the run before merging.

## 8. Performance Guidelines

### 8.1 Backend
- Use Redis for ephemeral data
- Batch database operations
- Async I/O for external calls
- Profile before optimizing

### 8.2 Frontend
- Lazy load components
- Optimize re-renders (React.memo)
- Debounce user inputs
- Minimize bundle size

---

**Remember**: This document defines the "what" and "how" of code standards. For workflow and process, see @CLAUDE.md.
