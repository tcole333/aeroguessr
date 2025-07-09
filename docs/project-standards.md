# Project Coding & Documentation Standards

This document defines coding conventions, architectural patterns, and documentation requirements for the Plane Game v4 codebase. For development workflow, see @CLAUDE.md.

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
- Max function length: 50 lines (extract helpers if larger)
- Use `pydantic.BaseModel` for data structures
- Async functions for all routes and I/O operations
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
- Functional components only (no class components)
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

## 2. Architecture Patterns

### 2.1 Backend Structure
```
backend/
├── app.py              # FastAPI app initialization
├── routes/             # API endpoints & WebSocket handlers
├── services/           # Business logic layer
├── schemas/            # Pydantic models
├── ingest/             # ADS-B data ingestion
├── features/           # Feature-specific modules
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
- **Integration**: Tests in `tests/integration/` using Docker containers
- **Frontend**: Tests alongside components: `*.test.tsx` using Vitest + Testing Library
- **Coverage**: Minimum 1% threshold (configured in `vitest.config.ts`)

## 3. Documentation Requirements

### 3.1 Code Documentation
- **Functions**: Document purpose, parameters, returns, exceptions
- **Complex Logic**: Inline comments explaining "why" not "what"
- **APIs**: OpenAPI annotations on all endpoints
- **Components**: JSDoc comments for props and behavior

### 3.2 Project Documentation
- **README**: Keep "Context for LLMs" section updated
- **API Changes**: Run `make openapi` and commit generated `types/api.ts`
- **WebSocket Changes**: Run `make ws-schema` and commit generated `types/ws.ts`
- **Architecture Changes**: Create/update ADR in `ADR/`
- **Issue Tracking**: Use GitHub Issues with provided templates for features, bugs, and tech debt

### 3.3 Type Generation
- **API Types**: Auto-generated from OpenAPI schema to `frontend/types/api.ts`
- **WebSocket Types**: Auto-generated from schema to `frontend/types/ws.ts`
- **Update Command**: `make openapi && make ws-schema` after backend changes

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
// Use console methods appropriately
console.debug('Component render details');
console.log('User action:', action);
console.warn('Deprecated API usage');
console.error('Failed to load map tiles:', error);
```

### 4.3 Log Output
- **Backend logs**: `logs/backend.log`
- **Frontend logs**: Currently in browser console (TODO: capture to `logs/frontend.log`)
- **Integration test logs**: Currently in `logs.txt` (TODO: move to `logs/integration.log`)
- **Format**: `[timestamp] [level] [module] message`

## 5. API & WebSocket Standards

### 5.1 REST API
- Version in URL: `/api/v0/`
- Resource-based naming: `/rooms`, `/players`
- Standard HTTP status codes
- Consistent error format:
```json
{
  "detail": "Error message",
  "code": "ERROR_CODE"
}
```

### 5.2 WebSocket Messages
- JSON format with `type` field
- Consistent naming: `snake_case`
- Include `timestamp` on server messages
- Document in `docs/ws_schema.yaml`

## 6. Environment & Configuration

### 6.1 Environment Variables
- Define in `.env.example` with descriptions
- Group by service (REDIS_, OPENSKY_, etc.)
- Required vs optional clearly marked
- No secrets in code or commits

### 6.2 Feature Flags
- Use environment variables: `FAKE_ADSB=1`
- Document behavior in README
- Default to production behavior

## 7. Quality Checks

### 7.1 Pre-commit Hooks
All code must pass:
- Python: Ruff (linting + formatting)
- TypeScript: ESLint + Prettier
- JSON/YAML: syntax validation
- File size limits
- No merge conflicts

### 7.2 CI Requirements
- Unit tests must pass
- Coverage threshold: 1% (minimal baseline)
- All linting checks green
- Docker builds succeed

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
