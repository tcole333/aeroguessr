# AeroGuessr

A real-time flight-guessing game on live ADS-B data over Boston Logan. The backend is FastAPI with Redis and an ADS-B ingest. The frontend is React, Vite, Zustand and Leaflet. The maintainer's instance runs on a Raspberry Pi and is served at aeroguessr.com. Anyone can self-host it from the published images.

Read before working:
- **Requirements:** [docs/PRD.md](docs/PRD.md).
- **Code layout, Redis keys, game engine:** [docs/architecture.md](docs/architecture.md).
- **The maintainer's Pi (aeroguessr.com):** [docs/deployment.md](docs/deployment.md).
- **Self-hosting** (published images, `selfhost/`): [docs/self-hosting.md](docs/self-hosting.md).
- **Tests:** [tests/README.md](tests/README.md).
- **Conventions:** [docs/project-standards.md](docs/project-standards.md).
- **The local setup:** [CONTRIBUTING.md](CONTRIBUTING.md).

Current work is epic #148 on GitHub.

## Rules that bite

- **Answer secrecy.**
  - No server message before `roundResult` may name a route's airports.
  - Planes go out only as `PublicPlaneState`, built by `backend/services/plane_visibility.py`.
  - `tests/integration/test_answer_secrecy.py` guards this.
- **Every Redis key needs a TTL.** Production Redis runs `noeviction`, so a key without one never leaves.
- **AeroAPI costs money.**
  - Only `backend/ingest/aeroapi_client.py` calls it, through the budget in `aeroapi_budget.py`, and only `board_refresher.py` uses that client.
  - Changes near it need call-count tests.
  - Never use a real key in tests.
- **Merging needs the maintainer's explicit approval: a merge to `main` deploys to their Pi within a minute.** The approval is either for that PR or a written standing approval that names a class of PRs and who may merge them. CI is advisory (no branch protection). After merging, confirm the deploy: `.deployed-commit` on the Pi should match `origin/main`, and the log should say "Deploy successful!" (docs/deployment.md).
- **Settings live in `backend/settings.py`.**
  - Native runs read the root `.env`. Tests never do: `tests/conftest.py` sets `AEROGUESSR_ENV_FILE` to empty.
  - A new setting goes in `settings.py` and in `.env.example`; a test enforces it.
  - Containers get the same file: on the Pi, Compose passes the root `.env` to the backend.
- **Lease test databases.** Sessions on one machine share a test Redis (127.0.0.1:6381 on the maintainer's Mac), and every test run flushes its database. Before each native test run, `export TEST_REDIS_URL=$(uv run python scripts/redis_lease.py lease)`: it returns your database and renews the lease, which lapses after 2 hours. Never pick a database by hand. A second run at the same time, such as a subagent's, needs its own lease (`--owner`).
- **Run local stacks through `make`.** `make start` and `make integration-test` run a Compose project named after the checkout, and `make demo` runs its own Redis container on free ports, so worktrees never share containers or volumes, and demo stacks never share ports. Every `make start` publishes port 80, so only one runs at a time. A bare `docker compose -f infra/...` uses the project `infra` from any checkout, and its `down -v` deletes whatever volumes that project holds. `selfhost/compose.yaml` is always `aeroguessr`; pass `-p` to run it from a worktree.

## Commands

```bash
scripts/worktree-setup.sh                        # once per fresh worktree: .venv (uv sync), node_modules
make demo                                        # run the game locally (synthetic planes, no AeroAPI); prints its URLs
uv run pytest -m "not integration" tests/        # unit tests, from the repo root (point pytest at tests/, not tests/backend/)
(cd frontend && npm run test:ci && npm run typecheck && npm run lint)
make integration-test                            # real Redis + live backend, in Docker
uv run pre-commit run --all-files
uv add --group dev <package>                     # a dev dependency (runtime: drop --group dev); commit uv.lock with it
make openapi && make ws-schema && (cd frontend && npm run gen:schema)   # after changing routes or WS messages
```

To see the app from a worktree, start `make demo` as a background task and open the `Game:` URL it prints with `preview_start`'s `url`. Don't use a `.claude/launch.json`: its ports are fixed, and the one in the main checkout runs that checkout's code, not yours. Stop the task when you're done. TaskStop sends SIGTERM, and `scripts/dev.sh` stops everything it started on SIGINT, SIGTERM or SIGHUP, even when it was started with `&`.

## Review

Before a PR merges, run one adversarial review round with the `qa` agent (`.claude/agents/qa.md`). It reports only to you. Fix what it marks blocker or should-fix. List its nits and follow-ups under "Follow-ups" in the PR description; they are filed as one issue when the PR merges.

## The maintainer's Pi

These commands reach aeroguessr.com's Pi. `pi-plane` is an SSH alias on the maintainer's machine, so only the maintainer can run them.

```bash
ssh pi-plane "tail -f /home/pi/plane-game-v4/logs/auto-update.log"       # watch a deploy
ssh pi-plane "cd /home/pi/plane-game-v4 && cat .deployed-commit"         # what is actually running
ssh pi-plane '/home/pi/plane-game-v4/scripts/auto-update.sh >> /home/pi/plane-game-v4/logs/auto-update.log 2>&1'   # deploy now
```
