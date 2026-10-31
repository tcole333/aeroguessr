# Infra

[docs/deployment.md](../docs/deployment.md), the aeroguessr.com runbook, covers the maintainer's Pi, the Compose stack, auto-deploy, the Cloudflare Tunnel, the ADS-B receiver and logs. Self-hosters use `selfhost/compose.yaml` instead ([docs/self-hosting.md](../docs/self-hosting.md)).

- **On the maintainer's Pi, run Compose with both files:** `docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml`. Without the Pi override, the ingest can't reach dump1090. Locally, `make start` uses the base file alone.
- **Names:** the Pi override fixes the project name `infra` and the `plane-game-*` container names, which the Pi's volume, network and runbook depend on. Locally, the Makefile runs each checkout as its own project (`scripts/checkout-env.sh`), so the base and test files fix no names and the test file publishes no ports.
- **The backend's settings come from the repo-root `.env`** (`env_file`). Compose's `environment:` holds only container wiring; defaults live in `backend/settings.py`.
- **Only nginx publishes a port (80).** Reach the backend through nginx (`curl localhost/healthz`) or by exec into the container.
- **On the maintainer's Pi, deploy with `scripts/auto-update.sh`.** It holds a lock and records `.deployed-commit`. To build by hand, stop `plane-game-update.timer` first.
- **Code reaches the Pi only through `main`.** Never copy files onto it, by rsync, scp or any other way. An edit in its checkout ships unnoticed while `.deployed-commit` still matches `origin/main`. Once a later commit touches the same file, the fast-forward fails, and every deploy after that fails until someone fixes the checkout by hand.
- **After deploying a change that could raise AeroAPI spend,** read the ingest's log (`docker logs plane-game-backend`):
  - every request logs a line with `today N/M result sets`;
  - warnings mark the daily cap being reached, or Redis errors denying requests.
- **Changes to `docker-compose.yml`** must keep the guarantees in `tests/deploy/test_compose_config.py`: Redis `noeviction` with no AOF, log caps and memory limits on every service, and the Pi's project and container names. `selfhost/compose.yaml`, the self-hosters' stack on the published images, keeps the same guarantees.
- **The frontend image proxies `/api/` itself** (`frontend/nginx/default.conf.template`) for the self-hosters' stack. Here `nginx.conf` routes `/api/` to the backend first, so that proxy goes unused.
