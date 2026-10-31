# Testing Strategy & Setup

How the test suites are organised, which fixtures they share, and how to run them locally and in
CI.

**Core principles:**

1.  **Separation:** unit tests (`tests/backend/`, `tests/deploy/` and `tests/scripts/`, no `integration` marker) run
    in-process with fakes. Integration tests (marker `integration`) talk to a real Redis, and most of them to a
    live backend.
2.  **Fixtures:** shared setup lives in `conftest.py` files (`tests/`, `tests/backend/`,
    `tests/integration/`).
3.  **Markers:** `@pytest.mark.integration` (usually as a module-level `pytestmark`) selects the
    integration suite; everything else is a unit test.
4.  **Automation:** `.github/workflows/ci.yml` runs both suites, plus ruff and the frontend checks,
    on every push to `main` and every pull request.

## 1. Test Types & Locations

| Location                                   | Type        | Needs                                   | Marker        |
| ------------------------------------------ | ----------- | --------------------------------------- | ------------- |
| `tests/backend/`                           | Unit        | Nothing (FakeRedis, mocks)              | _(none)_      |
| `tests/backend/services/*_integration.py` | Integration | A real Redis (`TEST_REDIS_URL`)         | `integration` |
| `tests/backend/ingest/` (AeroAPI budget, client, board refresher, demo and live mode) | Integration | A real Redis (`TEST_REDIS_URL`) | `integration` |
| `tests/backend/routes/` tests using `game_redis` | Both | FakeRedis, plus a real-Redis variant | `integration` on the real-Redis variant |
| `tests/integration/`                       | Integration | A live backend and the Redis it uses    | `integration` |
| `tests/deploy/`                            | Unit        | bash and git; `flock` for one test (Linux) | _(none)_   |
| `tests/scripts/`                           | Unit        | bash                                    | _(none)_      |
| `tests/scripts/test_redis_lease.py`        | Integration | A real Redis (`TEST_REDIS_URL`)         | `integration` |
| `frontend/src/**/*.test.ts(x)`              | Frontend    | Nothing (Vitest, jsdom, MSW)            | -             |

`tests/deploy/` runs the real `scripts/auto-update.sh` against a local git remote, with fake `docker` and `curl`. It also checks the guarantees both compose stacks keep (the Pi's in `infra/` and the self-hosters' in `selfhost/`), that the backend, the frontend, `selfhost/.env.example` and the self-hosting guide name one release version, and that the frontend image sets every variable its nginx config needs. `tests/scripts/` runs `scripts/check_test_skips.py` on files it writes to a temporary directory, checks `scripts/checkout-env.sh`'s project names and free ports, and leases a database with `scripts/redis_lease.py` on the server `TEST_REDIS_URL` names. Run the unit suite from `tests/`; from `tests/backend/`, these tests are never collected.

## 2. Key Fixtures

### 2.1 Unit Test Fixtures (`tests/backend/conftest.py`)

Function-scoped, so every test gets fresh state.

- `fake_redis_instance` -> `fakeredis.aioredis.FakeRedis`: a fresh in-memory Redis.
- `redis_client` -> `backend.utils.redis_async.RedisClient`: wraps `fake_redis_instance`, flushes
  it, and overrides the app's `get_redis` dependency for the test.
- `test_client` -> `httpx.AsyncClient`: talks to the FastAPI `app` in-process through
  `ASGIWebSocketTransport` (HTTP and WebSockets), using the overridden dependency.

### 2.2 Real-Redis Fixtures (`tests/conftest.py`)

Every test that needs a real Redis goes through these fixtures. They follow one contract:

- The database comes from **`TEST_REDIS_URL`** (e.g. `redis://127.0.0.1:6379/1`). If it is unset,
  the test **fails** with an explanation; it is never skipped.
- **Database 0 is refused**, because that is where dev stacks keep live game state.
- The fixture **flushes only that database**, before and after each test. Point `TEST_REDIS_URL`
  at a database nothing else uses; on a shared server, lease it (3.2).

Fixtures:

- `real_redis` -> `redis.asyncio.Redis` (`decode_responses=True`) on the test database.
- `real_redis_client` -> the app's `RedisClient`, configured through `REDIS_URL` exactly as in
  production (per-call connections on a shared pool), on the same database.

### 2.3 Live-Backend Fixtures and Helpers (`tests/integration/`)

- `integration_base_url` (session): `INTEGRATION_BASE_URL`, returned once the backend there
  answers `/healthz` with any HTTP response (status ignored). Fails when unset or when nothing
  answers within 30s.
- `integration_client` -> `httpx.AsyncClient` bound to that URL. It depends on `real_redis`, so
  every live-backend test starts and ends on a flushed database.
- `ws_helpers.wait_for_message(ws, type, **payload)` and
  `ws_helpers.wait_for_messages(ws, Expected(...), ...)`: read frames until the expected ones
  arrive, in any order, answering server pings. The backend interleaves `delta` frames (every
  second once planes exist), pings and other clients' broadcasts, so never assert on "the next
  frame". Unmatched frames are discarded, so collect messages the server sends together (e.g.
  `playerLeft` + `newHost`) in one `wait_for_messages` call. On timeout the error names what is
  missing and the last unmatched frames.
- `planes.seed_plane(redis, hex, origin=..., destination=...)`: stores a plane over Boston Logan
  with a fresh timestamp. The broadcast loop deletes planes outside the 250 km antenna range or
  older than 60s, so hand-built planes elsewhere can vanish mid-test. The server also rejects
  selections whose route does not touch the monitored airport (KBOS by default).

### 2.4 In-Process WebSockets (`tests/backend/routes/game_socket.py`)

- `game_socket(ws_path)` opens a game WebSocket on the in-process `app`.
  - It uses a client of its own, which sees the same dependency overrides as `test_client`.
  - Leaving the block sends `leave` and closes that client, which waits for the server's handler.
- Why raw `aconnect_ws` isn't enough: it returns without waiting for the handler.
  - Nothing waits for that handler until `test_client` closes, and closing waits only for the last
    socket opened on it.
  - Two nested raw sockets on one client fail outright.
  - A handler still cleaning up when Redis is torn down can hang the test (the `game_socket`
    docstring explains how).

  Use `game_socket` for every socket.
- Teardown order: in `tests/backend/routes/`, when a test uses `game_redis`, an autouse fixture
  sets it up before `test_client`. So `test_client` closes before the Redis fixtures flush and
  disconnect. It's a backstop, not a replacement for `game_socket`.

## 3. Running Tests

The git hooks from `uv run pre-commit install` run lint, formatting and the frontend typecheck on every
commit, and the test suites on `git push`: the backend unit suite on every push, the frontend
suite when the pushed commits change TypeScript. CI runs both suites on every push and pull
request. Run `uv run pre-commit install` again if your checkout's hooks predate the push hook or
the switch to uv. `uv run pre-commit run --all-files` runs only the commit hooks; add
`--hook-stage pre-push` to run the suites as a push does.

### 3.1 Unit tests

```bash
uv run pytest -m "not integration" tests/   # uv run first syncs .venv with uv.lock
```

In a fresh checkout or git worktree, run `scripts/worktree-setup.sh` first. It syncs the
checkout's `.venv` (`uv sync`) and sets up `frontend/node_modules`, which the frontend hooks need.

### 3.2 Integration tests, natively

Use a Redis database that nothing else uses (never a dev stack's db 0); both the backend and
the tests use it.

```bash
# Terminal 1: the backend under test, ignoring your .env (AEROGUESSR_ENV_FILE=)
export REDIS_URL=redis://127.0.0.1:6379/1
AEROGUESSR_ENV_FILE= HOST_DISCONNECT_CLAIM_WINDOW_SECONDS=2 \
  uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000

# Terminal 2: the suite
export TEST_REDIS_URL=redis://127.0.0.1:6379/1      # same database as the backend
export INTEGRATION_BASE_URL=http://127.0.0.1:8000
export HOST_DISCONNECT_CLAIM_WINDOW_SECONDS=2       # same value as the backend
uv run pytest -m integration tests/
```

Notes:

- Do not set `WS_BASE_URL` for the backend; tests connect to the `ws_url` the API returns.
- Do not run the ingest process (`backend.ingest.main`) against that database: its planes would
  show up in the delta assertions.
- `HOST_DISCONNECT_CLAIM_WINDOW_SECONDS` must match between backend and tests; the claim-host
  tests fail with an explanation when it is unset.
- On a test Redis that sessions share (127.0.0.1:6381 on the maintainer's Mac), lease the database
  instead of picking one, and give the backend the same URL and a free port:
  `export TEST_REDIS_URL=$(uv run python scripts/redis_lease.py lease)`.
  - Lease again before each run: it returns the same database and renews the lease, which lapses
    after 2 hours. `release` flushes the database and ends the lease; `list` shows the holders.
  - Only an empty database can be leased, so a lease never takes data that someone else left.
  - `scripts/worktree-setup.sh` leases one for its checkout. A second run from the same checkout
    at the same time, such as a subagent's or a loop's, needs its own: `--owner <name>`.
  - `make integration-test` (3.3) needs no lease: each checkout gets its own stack.

### 3.3 Integration tests, in docker-compose

```bash
make integration-test
```

This builds and starts `infra/docker-compose.test.yml`, waits for the backend inside its
container, runs `pytest -m integration` there, writes container logs to `logs/integration.log`,
tears the stack down, and exits non-zero if startup or any test failed. The compose file sets
`REDIS_URL`, `TEST_REDIS_URL` and `INTEGRATION_BASE_URL` for the `backend-test` container.

The stack runs as the checkout's own Compose project, `aeroguessr-<checkout directory>_test`,
and publishes no host ports. Runs from several worktrees can overlap, next to any local Redis or
API, and the teardown (`down -v --remove-orphans`) removes only that project's containers and
volumes.

### 3.4 CI

`.github/workflows/ci.yml` runs on push to `main` and on every pull request, whatever its base branch (so stacked PRs get CI):

- `ruff`: `ruff check .` and `ruff format --check .`
- `pre-commit`: `pre-commit run --all-files`, skipping the hooks other jobs run (ruff, ESLint,
  the typecheck, both test suites), Prettier (not enforced yet) and gitleaks. That leaves the
  file checks (whitespace, end of file, YAML/JSON/TOML syntax, files over 1 MB, merge markers,
  debugger statements), shellcheck on the shell scripts and actionlint on the workflows, which
  also shellchecks their `run:` scripts.
- `gitleaks`: scans the checked-out files, then only this pull request's or push's own
  commits, including what a merge commit adds. It runs with `--redact`, so a finding never
  prints the secret, and it fails if it can't list the commits.
- A separate workflow, `pr-title.yml`, checks that the PR title is a conventional commit
  (docs/project-standards.md 1.3), because a squash merge uses the title as the commit
  message. A single-commit PR squashes with its commit's message, so the check reads that too.
  Merge commits and rebase merges skip the title. Editing the title re-runs the check.
- `skip-guard`: `python scripts/check_test_skips.py` fails on a skipped test (`it.skip`,
  `test.skip`, `describe.skip`, the `{ skip: true }` option, `ctx.skip()`, `pytest.mark.skip`,
  `pytest.skip(`) unless the same line names an issue (`#123`); for Python, anywhere inside the
  skip's own call also counts. Conditional skips (`skipif`, `skipIf`), `xfail` and `it.todo`
  are not checked, and Vitest itself refuses `.only` when `CI` is set.
- `backend-unit`: `pytest -m "not integration" tests/` with a 50% coverage floor; coverage is
  uploaded to Codecov with the `unit` flag. Neither Codecov upload can fail its job, because
  pull requests from forks get no token.
- `backend-integration`: a Redis service and a uvicorn backend started by the job, then
  `pytest -m integration -v tests/`. No ingest service runs and no API keys are configured; the
  ingest tests run the ingest themselves for a few seconds, in demo mode or against a mocked
  AeroAPI, so the suite spends no API credits. The backend runs under `coverage run` and is
  stopped with SIGINT so its data is combined with the in-process tests' and uploaded with the
  `integration` flag; Codecov's patch check counts both uploads. The backend log is uploaded
  when the job fails.
- `frontend`: `npm ci`, `npm run lint`, `npm run typecheck`, `npm run test:ci`, `npm run build`.
  Lint fails above the `--max-warnings` cap in `frontend/package.json`. Nothing lowers the
  cap for you: lower it by hand when you remove warnings.
- `schema-drift`: reruns `make openapi && make ws-schema && (cd frontend && npm run gen:schema)`
  and fails if `git status` shows any change, so a stale or missing generated file fails the job
- `docker-images`: builds both images, so a broken Dockerfile fails here rather than on the Pi

`.github/workflows/release.yml` builds both images for linux/amd64 and linux/arm64, after starting the frontend image and checking that it serves the page. Pull requests that change a Dockerfile, the frontend's nginx config or the dependencies run it as a dry run, so a broken frontend config or an arm64-only break fails before a release. A `v*` tag publishes the images ([deployment.md](../docs/deployment.md#releases)).

CI is advisory: there is no branch protection, and the maintainer's Pi deploys whatever lands on `main`.

### 3.5 Frontend tests

```bash
cd frontend && npm run test:ci    # the whole suite, with coverage
cd frontend && npx vitest run src/features/map/__tests__/    # map performance budgets only
```

- Tests sit next to the code they test or in `__tests__/` folders, as `*.test.ts(x)`, and use Testing Library.
- They use the real store (`createRootStore()` in a `StoreContext.Provider`) and real child components, and fake only the network:
  - REST goes through MSW. `src/mocks/handlers.ts` answers `GET /api/v0/config`; a test adds the routes it calls with `server.use(...)`. MSW logs a request with no handler as an error and fails the request, but the test fails only if that error reaches it, so assert on what the request was for.
  - The WebSocket is `src/mocks/fakeWebSocket.ts`. Before each test, reset `FakeWebSocket.instances` and stub the global with it (`vi.stubGlobal('WebSocket', FakeWebSocket)`); play the server with `serverAccepts`, `serverSends` and `serverCloses`. After a test that connected the app's shared client, call `webSocketClient.destroy()`, or the next test's connect to the same URL reuses the old socket.
  - Some older tests still mock project code: `useStore`, child components, the `apiService` functions, the `useWebSocketManager` module, or `webSocketClient.send`. Move them to the real store when you change them.
- `vitest.setup.ts` clears `localStorage` after each test, because the store persists the session there.
- **Map performance budgets** keep map updates within the PRD's 300 ms target.
  - `src/features/map/__tests__/MapPerformance.test.tsx` mounts `MapView` with 100 and 200 fake planes and asserts the average update time.
  - `MapPerformance.canary.test.tsx` renders a deliberately slow marker and checks that the harness notices it, so the budgets can't pass vacuously.

## 4. Configuration

- **`pytest.ini`:** ignored paths, the `integration` marker, and a 60 s per-test timeout
  (pytest-timeout, a required plugin), so a hung test fails with a traceback instead of
  stalling the run. A test that needs longer can say so with `@pytest.mark.timeout(seconds)`.
- **`pyproject.toml`:** test dependencies (`pytest`, `pytest-asyncio`, `httpx`, `httpx-ws`,
  `fakeredis`, ...).

## 5. Guidance for Agents

- Unit setup: `tests/backend/conftest.py` and how `redis_client` overrides `get_redis` for
  `test_client`.
- Real Redis: use `real_redis` / `real_redis_client` from `tests/conftest.py`; do not add another
  fixture that flushes a database. In CI the live backend shares that database: seed planes with
  `planes.seed_plane`, and give tests that stage player presence their own keys
  (`private_presence_keys` in `tests/backend/ingest/conftest.py`), because the backend
  republishes `presence:active_rooms` every second.
- Ports: bind test servers (e.g. the synthetic ADS-B generator) to the `free_tcp_port` fixture,
  never a fixed port.
- Live backend: `tests/integration/conftest.py`, `ws_helpers.py` and `planes.py`.
- In-process WebSockets: open them with `game_socket` (2.4), not raw `aconnect_ws`, so the
  server's handler finishes before the fixtures close Redis.
- Test files mirror the `backend/` layout (e.g. `backend/routes/rooms.py` ->
  `tests/backend/routes/test_rooms.py`).
- No skips without an issue reference, on the same line as the skip:
  `@pytest.mark.skip(reason="#123 ...")` or `it.skip(...); // #123`. The `skip-guard` CI job
  checks the usual forms (3.4).
