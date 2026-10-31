# Contributing to AeroGuessr

Thanks for helping. AeroGuessr is a small alpha project with one maintainer, and issues and pull requests are welcome.

- **Bugs and ideas:** open an [issue](https://github.com/tcole333/aeroguessr/issues). For anything bigger than a small fix, open the issue first and say how you'd approach it, so we agree on the approach before you build it.
- **Security problems:** don't open an issue. [SECURITY.md](SECURITY.md) says how to report them privately.

## Set up

You need [uv](https://docs.astral.sh/uv/), Node 22, and Docker for Redis. uv fetches Python 3.12, the version `.python-version` pins, if it isn't installed. Demo mode makes up its own planes, so it needs no receiver and no API key.

```bash
scripts/worktree-setup.sh  # .venv (uv sync) and frontend/node_modules
uv run pre-commit install  # the git hooks
make demo                  # then open the game's URL it prints; Ctrl-C stops
```

`scripts/worktree-setup.sh` gets a fresh clone or git worktree ready in one command, and running it again is quick.
- It runs `uv sync`, which builds this checkout's own `.venv` from uv's cache, on the Python 3.12 that `.python-version` pins.
- It clones `frontend/node_modules` from a shared copy for the same `package-lock.json`, kept in `~/.cache/aeroguessr/`. Only the first checkout with a new lockfile runs `npm ci`. On APFS a clone takes no disk space until its files change, and each checkout's copy is its own.
- If 127.0.0.1:6381 runs a test Redis that a lease has marked as shared, it leases this checkout a database there for 2 hours (`scripts/redis_lease.py`). It never touches any other Redis.
- It prints the names and ports this checkout's stacks use, and the leased `TEST_REDIS_URL`.

`uv run` syncs `.venv` with `uv.lock` before it runs anything, so a pull that changes the dependencies needs no extra step. The git hooks run pre-commit from the `.venv` of the checkout that installed them, and worktrees share one set, so install them from the main checkout. In a clone whose hooks were installed before the switch to uv, run `uv run pre-commit install` once more.

`make demo` (`scripts/dev.sh`) starts this checkout's own Redis container. It then runs the API, the ingest and Vite in one terminal, and prefixes each line with its process.
- It uses synthetic planes and turns AeroAPI off, whatever your `.env` says.
- `make dev` does the same, with your `.env` as it is.
- It picks free ports, from 5173 for the game, 8000 for the API and 6379 for Redis, so stacks from several checkouts run at once. `DEV_WEB_PORT`, `DEV_API_PORT` and `DEV_REDIS_PORT` choose them instead.
- The Redis container, `aeroguessr-<checkout directory>-dev-redis`, stays after Ctrl-C, with its port and data.
- `NETWORK=1` lets phones on your LAN play at the address it prints.

The API and the ingest read the repo-root `.env`; copy [`.env.example`](.env.example) to start. Variables set in the shell win over it. [`backend/settings.py`](backend/settings.py) defines every setting.

`make start` builds the production Docker stack instead (`infra/`), at http://localhost. Like `make integration-test`, it runs as a Compose project named after the checkout's directory, so checkouts never share containers or volumes.

## Tests

```bash
uv run pytest -m "not integration" tests/        # backend and deploy unit tests, from the repo root
(cd frontend && npm run test:ci && npm run typecheck && npm run lint)
make integration-test                            # integration suite in Docker (real Redis, live backend)
uv run pre-commit run --all-files
```

[tests/README.md](tests/README.md) covers the fixtures, running the integration suite natively, and CI.
- Test behaviour, not implementation.
- Backend tests mirror the `backend/` layout under `tests/backend/`.
- Don't skip a test without an issue reference.

## Rules every change keeps

- **Answer secrecy.** No server message before `roundResult` may name a route's airports.
  - Planes go out only as `PublicPlaneState`, built by `backend/services/plane_visibility.py`.
  - `tests/integration/test_answer_secrecy.py` guards this. [docs/PRD.md](docs/PRD.md) §5.2 has the requirement.
- **Every Redis key needs a TTL.** Production Redis runs `noeviction`, so a key without one never leaves. Add new keys to the key table in [docs/architecture.md](docs/architecture.md#redis-keys).
- **AeroAPI costs money.**
  - Never put a real key in a test, a fixture, a log or a commit. Leave `FLIGHTAWARE_API_KEY` empty in development: with no key, no AeroAPI request of any kind is made.
  - Only `backend/ingest/aeroapi_client.py` calls AeroAPI, through the budget in `aeroapi_budget.py`, and only `board_refresher.py` uses that client.
  - A change near it needs call-count tests.
- **Settings live in `backend/settings.py`.** A new setting also goes in `.env.example`; `tests/backend/test_settings.py` enforces it.
- **Self-hosters run the published images** through `selfhost/compose.yaml`, and the frontend image's nginx proxies the API for them.
  - Keep both working, and keep `tests/deploy/` green.
  - A setting self-hosters need also belongs in `selfhost/.env.example` and [docs/self-hosting.md](docs/self-hosting.md).

## Conventions

- **Commits:** small, in the [Conventional Commits](https://www.conventionalcommits.org) form `type(scope): description`, for example `fix(ingest): drop planes with no position`. [docs/project-standards.md](docs/project-standards.md#13-commit-messages) lists the types.
- **Pull request titles** follow the same form, with the issue number: `feat: plane type icons (#42)`. `.github/workflows/pr-title.yml` checks the form, since a squash merge uses the title as the commit message.
- **Code style:** [docs/project-standards.md](docs/project-standards.md). On every commit, pre-commit runs Ruff, ESLint, Prettier, the frontend typecheck, gitleaks, shellcheck and actionlint; on `git push` it runs the test suites ([tests/README.md](tests/README.md#3-running-tests)).
- **Docs:** each fact lives in one long-lived doc; update that one and link to it from elsewhere. Plans and status belong in issues and pull requests, not in the repo.

## Before you open a pull request

- [ ] `uv run pre-commit run --all-files` passes.
- [ ] The unit tests pass, and the frontend checks pass if you touched `frontend/`.
- [ ] After changing a backend route or a WebSocket message, you regenerated the contract and the frontend types (below) and committed them.
- [ ] The docs that hold the facts you changed are updated.
- [ ] The description says what changed, why, and how you tested it.

CI runs on every pull request, including one stacked on another PR's branch (`.github/workflows/ci.yml`). A pull request that changes a Dockerfile, the frontend's nginx config or the dependencies also builds the release images for amd64 and arm64 (`.github/workflows/release.yml`).

## Common tasks

**Regenerate the API contract and the frontend types** after changing backend routes or messages:

```bash
make openapi && make ws-schema
(cd frontend && npm run gen:schema)
```

Run them in that order: `gen:schema` alone rebuilds the types from whatever YAML is committed.

**Regenerate the airport list.** `data/airports.json` (about 3,000 airports) is the game's single airport list:
- backend scoring uses it, so IATA `ORD` and ICAO `KORD` are the same airport;
- frontend autocomplete uses it;
- it decides which planes are playable.

The backend refuses to start without it.

```bash
uv run python backend/scripts/populate_airports_data.py
```

That rewrites the file from OurAirports: large airports, plus medium airports with scheduled service, that have an IATA code. Review the diff before committing; airports that drop out stop being playable.

**Replay a capture** instead of synthetic planes. Set `FAKE_ADSB=1`, and `FAKE_ADSB_FILE` to an SBS-1 capture (`.sbs` or `.sbs.gz`) recorded near `CENTER_LAT`/`CENTER_LON`, in `.env`. Optionally set `FAKE_ADSB_SPEED=5`. Then run `make dev`; `make demo` always uses synthetic planes. `sample_data/sbs_parser_fixtures.sbs` is a parser fixture, not a replayable capture.

## Notes

- **Map tiles:** the basemap is an [OpenFreeMap](https://openfreemap.org) vector style (Positron by default), rendered with MapLibre GL.
  - It needs no API key, but it has no SLA, and the browser needs WebGL2.
  - The OpenFreeMap / OpenMapTiles / OpenStreetMap attribution must stay visible.
  - `MAP_STYLE_URL` switches the style without a rebuild. Another provider also needs `OPENFREEMAP_ATTRIBUTION` in `backend/services/client_config.py` updated.
- **FlightAware AeroAPI:** routes come from the monitored airport's AeroAPI boards.
  - Requests happen only while someone is playing, and a daily cap limits them (25 result sets by default).
- **Claude Code:** the `CLAUDE.md` files describe the same rules for agents. `.claude/agents/qa.md` is an adversarial reviewer: run it on your pull request before asking for a merge. Anything about `ssh pi-plane` or `/home/pi` concerns the maintainer's aeroguessr.com instance, which only the maintainer can reach.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE). The exception is material under another license that [NOTICE.md](NOTICE.md) lists.
