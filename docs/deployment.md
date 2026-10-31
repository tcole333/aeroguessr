# Deployment: the aeroguessr.com runbook

This is the maintainer's runbook for aeroguessr.com. Its hosts, paths and commands belong to that one instance, and only the maintainer can reach them. **To run AeroGuessr on your own receiver, follow [self-hosting.md](self-hosting.md) instead.**

aeroguessr.com runs on a Raspberry Pi in Boston. The Pi has its own ADS-B receiver and serves the site through a Cloudflare Tunnel. Every merge to `main` deploys itself within a minute. For how the pieces fit together, see [architecture.md](architecture.md).

## The Pi

| | |
|---|---|
| Host | Raspberry Pi 4 Model B, 3.7 GB RAM, 117 GB SD card |
| OS | Debian 12 (bookworm), kernel 6.6 (`rpt-rpi-v8`) |
| Address | 192.168.1.181; `ssh pi-plane` (alias in `~/.ssh/config`) |
| Checkout | `/home/pi/plane-game-v4` |
| Receiver | RTL-SDR (Realtek RTL2838) with `dump1090-mutability` |
| GitHub access | read-only deploy key `/home/pi/.ssh/id_ed25519` ("pi-plane-deploy") |

## Compose stack

Always use both files. The Pi override points the ingest at the host's dump1090; without it, the ingest uses `ADSB_HOST=127.0.0.1` and gets no planes.

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml <command>
```

- **Services:** `nginx`, `frontend`, `backend` (API and ingest under supervisord) and `redis`.
  - Only nginx publishes a port (80). To reach the backend directly, go through nginx (`curl localhost/healthz`) or exec into the container.
- **Project and container names:** the Pi override fixes the Compose project name `infra` and the container names `plane-game-nginx`, `-frontend`, `-backend` and `-redis`.
  - The Redis volume `infra_redis-data`, which holds the AeroAPI budget counters, and the network belong to that project. Under another project name, Compose would start an empty volume.
  - Elsewhere, `make start` names the project after the checkout's directory, so local stacks never share these names.
- **Images** are built on the Pi from the repo root context (`backend/Dockerfile`, `frontend/Dockerfile`).
  - Docker's layer cache makes a deploy with no dependency changes take about 10 s.
  - BuildKit cache mounts keep npm and uv downloads, so a dependency change doesn't download everything again.
  - The backend build copies uv from the `ghcr.io/astral-sh/uv` image pinned in `backend/Dockerfile`, so the Pi pulls that image as well as `python:3.12-slim`. The Pi itself needs no Python tooling.
- **Container logs:** json-file, capped at `max-size: 10m` × `max-file: 3` for every service.
- **Memory limits:** `mem_limit` is set per service: backend 1g, redis 512m, frontend and nginx 64m.
  - **They are not enforced yet.** Raspberry Pi OS boots with `cgroup_disable=memory`, so Docker discards them, and `docker info` warns "No memory limit support".
  - To enforce them, append ` cgroup_enable=memory cgroup_memory=1` to the single line in `/boot/firmware/cmdline.txt`, then reboot.
- **Redis** runs `maxmemory 256mb`, `maxmemory-policy noeviction`, no AOF, and the default RDB snapshots.
  - Every key has a TTL and the dataset is a few MB, so the cap is only a safety net.
  - `noeviction` keeps the AeroAPI budget counters from being evicted.
  - With no AOF, there are no per-second writes to the SD card. The snapshot (a few KB) keeps the counters across restarts.

### Environment

The backend container reads its settings from the repo-root `.env` (`env_file` in `infra/docker-compose.yml`). Native runs read the same file.
- **On the Pi** it is `/home/pi/plane-game-v4/.env`, untracked, and it holds `FLIGHTAWARE_API_KEY`. [`.env.example`](../.env.example) lists every setting.
- **What wins:** Compose sets `REDIS_URL` and, in the Pi override, `ADSB_HOST`, and both win over the file. Anything the file leaves out uses the defaults in `backend/settings.py`. A missing `.env` is allowed.
- **Applying a change:** a deploy only runs for a new commit. After editing `.env`, run `docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml up -d`; Compose recreates the backend with the new values.
- **Leftovers:** `infra/.env` and `.env.pi` on the Pi are no longer read.

## Auto-deploy

A systemd timer runs `scripts/auto-update.sh` every minute. Builds happen on the Pi itself; there is no registry and no CI deploy step.

Each run of the script:
1. Takes a lock (`.auto-update.lock`), so a manual run cannot build alongside a timer run.
2. Trims `logs/auto-update.log` to its last 1 MB once it passes 5 MB.
   - The trim happens in place, because `logs/` is a root-owned bind mount.
3. Fetches `origin/main` and compares it with `.deployed-commit`.
   - That file holds the commit whose images were last built and started.
   - If they match, the run logs "Already up to date" and stops.
4. Fast-forwards the checkout (`git merge --ff-only`).
   - A dirty or diverged checkout makes the merge fail. The log shows git's error, and the run retries with backoff until someone fixes the checkout.
   - If `main` was rewound, the log says "Cannot fast-forward … fix the checkout by hand".
5. Builds and starts the containers (`up -d`), then writes `.deployed-commit`.
   - If this step fails, the next runs retry with backoff: immediately, then after 1, 3, 7, 15 and 31 minutes, then hourly.
   - `.deploy-attempts` tracks the retries, and the log says "failed to deploy N times".
6. Waits up to 60 s for the backend's `/readyz`, checks `/healthz` through nginx, and logs "Deploy successful!".
   - A readiness failure is logged but not retried, because rebuilding the same commit would not fix it.
7. Prunes dangling images. The build cache stays.

The systemd units are not in the repo. On the Pi they are:

```ini
# /etc/systemd/system/plane-game-update.service
[Unit]
Description=Plane Game Auto Update
After=network.target docker.service

[Service]
Type=oneshot
User=pi
WorkingDirectory=/home/pi/plane-game-v4
ExecStart=/home/pi/plane-game-v4/scripts/auto-update.sh
StandardOutput=append:/home/pi/plane-game-v4/logs/auto-update.log
StandardError=append:/home/pi/plane-game-v4/logs/auto-update.log

# /etc/systemd/system/plane-game-update.timer
[Unit]
Description=Run Plane Game Auto Update every 1 minute

[Timer]
OnBootSec=2min
OnUnitActiveSec=1min
Persistent=true

[Install]
WantedBy=timers.target
```

### Checking a deploy

A merge to `main` is not proof of a deploy. HEAD moves before the build, so compare `.deployed-commit` with `origin/main` instead.

```bash
ssh pi-plane "cd /home/pi/plane-game-v4 && cat .deployed-commit && git rev-parse origin/main"
ssh pi-plane "tail -50 /home/pi/plane-game-v4/logs/auto-update.log"
ssh pi-plane "systemctl list-timers | grep plane"
curl -s https://aeroguessr.com/readyz
```

### Deploying by hand

Run the script itself. It holds the lock and records the result. Only timer runs write to `auto-update.log`, so append a manual run yourself:

```bash
ssh pi-plane '/home/pi/plane-game-v4/scripts/auto-update.sh >> /home/pi/plane-game-v4/logs/auto-update.log 2>&1'
```

If you build by hand instead, stop the timer first. Otherwise a timer run sees the pulled commit as not yet deployed and builds it at the same time.

```bash
sudo systemctl stop plane-game-update.timer
cd /home/pi/plane-game-v4 && git pull --ff-only origin main
docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml up -d --build
sudo systemctl start plane-game-update.timer   # the next run rebuilds once from cache and records the commit
```

### Rolling back

Prefer pushing a revert to `main`; the timer deploys it like any other commit. To roll back on the Pi alone, stop the timer first. Otherwise a run that is retrying a deploy fast-forwards back to `origin/main`.

```bash
sudo systemctl stop plane-game-update.timer
cd /home/pi/plane-game-v4 && git reset --hard <sha>
docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml up -d --build
sudo systemctl start plane-game-update.timer   # once main has the fix
```

`.deployed-commit` still holds `origin/main` after a local rollback, so the check above reports the Pi as current. Use `docker images` and `git log -1` on the Pi instead.

## Releases

Self-hosters run published images through [`selfhost/compose.yaml`](../selfhost/compose.yaml); [self-hosting.md](self-hosting.md) is their guide. The Pi doesn't use these images, because it builds from source.

[`.github/workflows/release.yml`](../.github/workflows/release.yml) builds the backend and frontend images for linux/amd64 and linux/arm64.
- Before building, it starts the frontend image and checks that it serves the page.
- On a `v*` tag it pushes both to GHCR as `ghcr.io/<owner>/aeroguessr-backend` and `-frontend`, tagged with the version and `latest`.
- Once both are pushed, it creates the GitHub release, with generated notes. A version with a hyphen, such as `0.1.0-alpha.1`, makes a pre-release.

To release:
1. In one PR, set the new version in `pyproject.toml`, `frontend/package.json`, `selfhost/.env.example` and the quickstart in `docs/self-hosting.md`.
   - `npm version <version> --no-git-tag-version` in `frontend/` also updates the lockfile.
   - `tests/deploy/test_release_version.py` fails until all of them agree. The workflow refuses a tag that doesn't match all of them, too.
2. After it merges, tag that commit and push the tag: `git tag v<version> <sha> && git push origin v<version>`.
3. If one image job fails, the other image may already be pushed. Fix the cause and re-run the failed job; the release is created only once both succeed.
4. Edit the generated release notes: say what changed for self-hosters, and whether `compose.yaml` or `.env.example` changed.
5. After the first release, check that both GHCR packages are public (each package's settings → Change visibility).

Other runs only build, as a dry run:
- pull requests that change a Dockerfile, the frontend's nginx config or the dependencies;
- a manual run (Actions → Release images → Run workflow) from a branch.

A manual run from a tag publishes that tag again, without moving `latest`.

## Public access: Cloudflare Tunnel

`cloudflared` runs on the Pi as `cloudflared.service`. That unit is the repo's [`infra/cloudflared.service`](../infra/cloudflared.service), and it runs `cloudflared tunnel --no-autoupdate run` as `pi`.

It reads `/home/pi/.cloudflared/config.yml`, which is not in the repo. That config routes:
- every hostname to `http://localhost:80` (nginx);
- an SSH hostname to `ssh://localhost:22` (the hostname is in that config, not in this public repo).

[`infra/cloudflared-config.yml`](../infra/cloudflared-config.yml) is a per-path alternative, and the Pi does not use it. Its `/ws/*` rule matches no route, because WebSockets go through `/api/`.

**Setting up a tunnel from scratch.** `scripts/setup-cloudflare-tunnel.sh` installs cloudflared, logs in, creates the tunnel, routes DNS and writes a catch-all config. It differs from the Pi's setup in three ways:
- it installs its own systemd unit, not `infra/cloudflared.service`, so it lacks `Requires=docker.service` and the hardening;
- its config has no ssh route;
- the compose command it prints omits the Pi override.

By hand, the steps are:

```bash
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared-linux-arm64.deb
cloudflared tunnel login                        # opens a browser; from SSH, open the printed URL elsewhere
cloudflared tunnel create aeroguessr
cloudflared tunnel route dns aeroguessr aeroguessr.com
cloudflared tunnel route dns aeroguessr www.aeroguessr.com
# write /home/pi/.cloudflared/config.yml: tunnel id, credentials-file, ingress -> http://localhost:80
sudo cp /home/pi/plane-game-v4/infra/cloudflared.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now cloudflared
```

**Troubleshooting the tunnel:**
- `sudo journalctl -u cloudflared -n 50`
- `cloudflared tunnel list`
- check the origin directly: `curl -s localhost/healthz`
- If DNS doesn't resolve, check the records in the Cloudflare dashboard and allow a few minutes to propagate.
- Cloudflare terminates TLS, so its SSL mode must be "Full" or "Flexible".

## ADS-B receiver

`dump1090-mutability` decodes from the RTL-SDR, serves SBS-1 on TCP 30003 for the ingest, and has a web map on port 8080. It is configured in `/etc/default/dump1090-mutability`:

```bash
START_DUMP1090="yes"
DEVICE=""                     # auto-detect the RTL-SDR
GAIN="max"                    # 49.6 dB
SBS_OUTPUT_PORT="30003"       # the ingest connects here
NET_HTTP_PORT=8080
JSON_DIR="/run/dump1090-mutability"
JSON_INTERVAL="1"
MAX_RANGE="300"               # nautical miles
```

`dump1090-http.service` serves the JSON files. Checks:

```bash
sudo systemctl status dump1090-mutability dump1090-http
lsusb | grep -i rtl
timeout 5 bash -c 'exec 3<>/dev/tcp/localhost/30003; head -3 <&3'    # live SBS-1 lines
curl -s http://localhost:8080/stats.json | python3 -m json.tool
sudo systemctl restart dump1090-mutability dump1090-http
```

If the game shows no planes but dump1090 has traffic:
- check `/readyz`: it returns 503 with a `reason` when the ingest is not heartbeating or has no connection to the feed;
- read the ingest's log lines in `docker logs plane-game-backend`.

## Logs

| Log | Where | Bounded by |
|---|---|---|
| Container stdout (API, ingest, nginx, redis) | `docker logs <container>` | Docker json-file, 10 MB × 3 |
| API log file | `logs/backend.log` | the app, 5 MB rotating, 1 backup |
| Deploys | `logs/auto-update.log` | `auto-update.sh`, trimmed to 1 MB past 5 MB |

[`infra/logrotate.d/plane-game`](../infra/logrotate.d/plane-game) and `scripts/setup-logrotate.sh` exist, but the Pi has no logrotate config installed. The table above is what actually bounds each log.

## Troubleshooting

```bash
cd /home/pi/plane-game-v4
docker ps --format '{{.Names}} {{.Status}}'
docker logs plane-game-backend --tail 100
curl -s localhost/readyz          # through nginx; shows the reason when not ready
docker exec plane-game-redis redis-cli INFO memory | grep used_memory_human
docker system df
free -h && df -h /
```
