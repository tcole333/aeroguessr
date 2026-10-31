# Self-hosting

Run AeroGuessr on your own ADS-B receiver, so you and your friends guess the flights over your house. You need a working feeder and Docker; the game runs from two files and published images, with nothing to build.

This is an alpha. [Known limitations](#known-limitations) lists what doesn't work yet.

## What you need

- **A receiver:** an RTL-SDR USB dongle (for example an RTL-SDR Blog V4 or a FlightAware Pro Stick) and a 1090 MHz antenna. Higher and outdoors means more planes.
- **A feeder** that decodes ADS-B and serves SBS (BaseStation) output on TCP port 30003. These all do:
  - PiAware (`dump1090-fa`);
  - `readsb`;
  - ultrafeeder, including the adsb.im image.

  AeroGuessr reads that output and never touches the SDR, so it runs next to your feeder without interrupting what the feeder sends to FlightAware or anyone else.
- **A computer:** a Raspberry Pi 4 or 5 with 2 GB of RAM or more, or any Linux machine, usually the one the feeder runs on.
  - **It needs a 64-bit OS.** The images are built for `linux/arm64` and `linux/amd64`. Check with `dpkg --print-architecture` (or `docker version --format '{{.Server.Arch}}'`), which must print `arm64` or `amd64`.
  - Don't rely on `uname -m`. A Pi 4 or 5 running 32-bit Raspberry Pi OS boots a 64-bit kernel, so it prints `aarch64` even though Docker there is 32-bit. Some feeder SD-card images are 32-bit.
  - On a 32-bit system, pulling fails with `no matching manifest for linux/arm/v7`.
  - The game uses about 350 MB of RAM (the backend about 290 MB) and little CPU.
- **Docker** Engine 20.10 or newer, with the Compose plugin. If `docker compose version` already prints v2, as it does on adsb.im, skip this. Otherwise see [Install Docker Engine](https://docs.docker.com/engine/install/). On Raspberry Pi OS and Debian, Docker's convenience script is the quick way:

  ```bash
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER"    # then log out and back in
  ```

## Quickstart

Download the compose file and the settings template for the release you want. Releases are listed on the [releases page](https://github.com/tcole333/aeroguessr/releases).

```bash
mkdir -p ~/aeroguessr && cd ~/aeroguessr
VERSION=0.1.0-alpha.1
curl -fsSL -o compose.yaml "https://raw.githubusercontent.com/tcole333/aeroguessr/v$VERSION/selfhost/compose.yaml"
curl -fsSL -o .env "https://raw.githubusercontent.com/tcole333/aeroguessr/v$VERSION/selfhost/.env.example"
```

Edit `.env`. At least set:
- `CENTER_LAT` and `CENTER_LON`, your antenna's position. The map opens there, and browsers see it rounded to about 1 km. To keep even that private, use a nearby public point such as your airport;
- `MONITORED_AIRPORT_ICAO`, your airport;
- `FLIGHTAWARE_API_KEY`: live rounds need one ([Route data](#route-data)). Demo mode doesn't.

The game is served on port 8088 (`HTTP_PORT`), because a feeder's web interface often holds port 80. [Configuration](#configuration) covers every setting. Then start it:

```bash
docker compose up -d
```

The first start downloads about 200 MB of images. `docker compose up -d` returns once the backend is healthy. Then open `http://<this machine's address>:8088/` from any device on your network, for example `http://raspberrypi.local:8088/`.

Check that it found your feeder:

```bash
curl -s http://localhost:8088/readyz
```

`{"status":"ready",...}` means the ingest is connected to your feeder. Planes appear on the map within a few seconds. If it says `not_ready`, see [Troubleshooting](#troubleshooting).

### Try it without a receiver

Set `FAKE_ADSB=1` in `.env` and run `docker compose up -d`. The backend then makes up its own planes and never calls AeroAPI. They fly in to your `CENTER_LAT`/`CENTER_LON`, with routes to your `MONITORED_AIRPORT_ICAO`, so every one of them is playable. Set `FAKE_ADSB=0` and run `docker compose up -d` again to switch to your feeder.

## Configuration

Settings live in `.env`, next to `compose.yaml`. After changing one, run `docker compose up -d`; Compose recreates the containers whose settings changed.

The template holds the settings a self-hoster usually changes. The repo's root [`.env.example`](../.env.example) lists every setting the backend reads, such as `MAP_STYLE_URL` for the basemap style. [`backend/settings.py`](../backend/settings.py) is the source of truth for their defaults. Any of them can go in `.env`.

| Setting | Template value | What it does |
|---|---|---|
| `AEROGUESSR_VERSION` | the template's release | Which images to run. See [Updating](#updating). |
| `HTTP_PORT` | `8088` | The port the game is served on. Set `80` to drop the port from the URL if nothing else on the machine uses it. |
| `CENTER_LAT`, `CENTER_LON` | Boston Logan | Your antenna's position in decimal degrees. It centres the position smoothing, the range filter and the map; browsers see it rounded to about 1 km. |
| `MAX_ANTENNA_RANGE_KM` | `250` | Planes farther than this from the centre leave the map. |
| `MONITORED_AIRPORT_ICAO` | `KBOS` | The airport rounds are about, labelled on the map: a 4-letter ICAO code in capitals. Pick one with scheduled airline service whose traffic your antenna sees. |
| `ADSB_HOST` | `host.docker.internal` | Where your feeder's SBS output is. `host.docker.internal` is the machine Docker runs on. See [A feeder in Docker](#a-feeder-in-docker). |
| `ADSB_PORT` | `30003` | The SBS port. |
| `FAKE_ADSB` | `0` | `1` replaces your feeder with generated planes. |
| `FAKE_ADSB_FILE` | `synthetic` | With `FAKE_ADSB=1`, `synthetic` makes planes up around your centre. |
| `FLIGHTAWARE_API_KEY` | empty | Your AeroAPI key. See [Route data](#route-data). |
| `AEROAPI_MONTHLY_BUDGET_USD` | `5.00` | The AeroAPI spend the daily request cap is derived from. |

Keep your own Compose changes in one `compose.override.yaml` next to `compose.yaml`, never in `compose.yaml` itself. Compose reads the override automatically when you run `docker compose` in the directory without `-f`. When you update, you replace `compose.yaml` with the new release's copy. The recipes below each add to that one file.

### A feeder in Docker

A feeder installed on the machine itself, such as PiAware's `dump1090-fa` or the `readsb` package, works with the default `ADSB_HOST=host.docker.internal`.

A feeder that runs in a container, such as ultrafeeder or anything on an adsb.im image, needs one more step. Docker drops traffic between its networks, even through a port the feeder publishes on the host. So the backend has to join the feeder's network:

1. Add the network to `compose.override.yaml`:

   ```yaml
   services:
     backend:
       networks: [default, feeder]

   networks:
     feeder:
       name: adsb_im_bridge    # adsb.im's network; for another feeder, find it with docker network ls
       external: true
   ```

2. Set `ADSB_HOST` in `.env` to the feeder's container name. On adsb.im that is `ultrafeeder`; `docker ps` lists the names.
3. Run `docker compose up -d`.

## Route data

A plane is playable once its route is known, and only when the route starts or ends at `MONITORED_AIRPORT_ICAO`. Players guess the other end, which must be in the game's list of about 3,000 airports with scheduled service. Overflights are never playable.

Routes come from FlightAware AeroAPI: the backend reads your airport's arrival and departure boards.
- **Live rounds need an AeroAPI key: it is the only route source.** With no key, the map shows your planes but none of them can be played. Demo mode (`FAKE_ADSB=1`) needs no key. A free route source is possible future work.
- **Get a key** from the [AeroAPI portal](https://www.flightaware.com/aeroapi/portal). Each self-hosted instance uses its own key, under FlightAware's terms. Put it in `FLIGHTAWARE_API_KEY`.
- **Cost:** AeroAPI bills $0.005 per result set of 15 flights.
  - The backend requests boards only while someone is playing. The first fill comes within about 15 seconds of a player joining, and refreshes stop 15 minutes after the last game action (`ENRICHMENT_IDLE_CUTOFF_MINUTES`).
  - Every request first reserves its pages against a daily cap derived from `AEROAPI_MONTHLY_BUDGET_USD`, less a 20% safety margin, spread over 31 days. The default $5.00 gives 25 result sets a day, and $10.00 gives 51.
  - The cap holds however many people play, so exposing the game publicly can't raise the bill past it. The counters live in Redis, so they survive restarts.
- **FlightAware feeders** get a monthly AeroAPI credit on the account they feed with, $10 at the time of writing. If yours does, set `AEROAPI_MONTHLY_BUDGET_USD=10.00`. Your FlightAware account shows the credit.

The root `.env.example` documents the remaining spend settings: `ENRICHMENT_ENABLED`, `AEROAPI_BUDGET_SAFETY_MARGIN`, `AEROAPI_DAILY_RESULT_SET_CAP` and `AEROAPI_RESULT_SETS_PER_MINUTE`.

## Access

By default the game is served at `http://<this machine's address>:<HTTP_PORT>/`.
- On a home network behind a router, that reaches your local network only.
- On a machine with a public IPv4 or IPv6 address, it reaches the internet too. Docker's published ports bypass host firewalls such as ufw.

The game has no accounts: anyone who can open the page can create and join rooms.
- The API's rate limit (10 requests a second, bursts of 20) counts per address, as on aeroguessr.com.
- Behind a tunnel, every player arrives from the tunnel's address, so the limit applies to all of them together.

Both options below give you HTTPS. The game's WebSocket switches to `wss://` on its own when the page is served over HTTPS.

### Cloudflare Tunnel

This needs a Cloudflare account and a domain on Cloudflare. Below, `$DOMAIN` stands for the hostname you'll use, such as `game.example.com`.

1. In the Cloudflare dashboard, [create a remotely managed tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/get-started/create-remote-tunnel/) of type cloudflared, and copy its token.
2. Route a public hostname, `$DOMAIN`, through the tunnel to the service `http://frontend:80`. That is the container's own port, whatever `HTTP_PORT` is.
3. Put the token in its own file, `tunnel.env`, next to `compose.yaml`. Keeping it out of `.env` keeps it away from the backend, which reads every variable in `.env`.

   ```bash
   echo 'TUNNEL_TOKEN=<the token>' > tunnel.env && chmod 600 tunnel.env
   ```

4. Add cloudflared to `compose.override.yaml`:

   ```yaml
   services:
     cloudflared:
       image: cloudflare/cloudflared:latest
       command: tunnel --no-autoupdate run
       env_file: tunnel.env
       depends_on: [frontend]
       restart: unless-stopped
       mem_limit: 128m
       logging:
         driver: json-file
         options: { max-size: "10m", max-file: "3" }
   ```

5. Run `docker compose up -d` and open `https://$DOMAIN/`.

### Tailscale Funnel

With [Tailscale](https://tailscale.com/download) on the host, Funnel serves the game at `https://<machine>.<tailnet>.ts.net/`. Use your `HTTP_PORT`:

```bash
sudo tailscale funnel --bg 8088
```

The first run prints a link if Funnel isn't enabled for your tailnet yet. To share the game only with devices on your tailnet, use `tailscale serve --bg 8088` instead. `tailscale funnel reset` stops it.

## Updating

`AEROGUESSR_VERSION` in `.env` pins both images. Each release also has its own `compose.yaml`. Read the release notes on the [releases page](https://github.com/tcole333/aeroguessr/releases), then:

```bash
cd ~/aeroguessr
OLD=$(sed -n 's/^AEROGUESSR_VERSION=//p' .env)
VERSION=0.1.0-alpha.2    # the release to move to
curl -fsSL -o compose.yaml "https://raw.githubusercontent.com/tcole333/aeroguessr/v$VERSION/selfhost/compose.yaml"
sed -i "s/^AEROGUESSR_VERSION=.*/AEROGUESSR_VERSION=$VERSION/" .env
docker compose pull && docker compose up -d
docker image rm "ghcr.io/tcole333/aeroguessr-backend:$OLD" "ghcr.io/tcole333/aeroguessr-frontend:$OLD"   # optional: frees about 400 MB
```

- Compare your `.env` with the new release's `selfhost/.env.example` for new settings.
- To go back, set the previous version in `.env`, download that release's `compose.yaml`, and run `docker compose up -d`.
- Each image is also tagged `latest`, but the compose file always uses the pinned version.

Redis keeps its data in the `aeroguessr_redis-data` volume across updates. `docker compose down` stops the game and keeps the volume. `docker compose down -v` deletes it, including the AeroAPI spend counters, so today's spend would start again from zero.

## Troubleshooting

Start with:

```bash
docker compose ps                          # every service should be "healthy"
curl -s http://localhost:8088/readyz       # use your HTTP_PORT
docker compose logs --tail 100 backend
```

A bug report should name the version you run. `curl -s http://localhost:8088/healthz` prints it, and in a game the settings tab (Terminal, in Chart Mode) shows it.

`/readyz` answers 200 when the game can run, and 503 with a `reason` when it can't. Its `checks.ingest` says what is wrong:

| `checks.ingest` | Meaning | What to check |
|---|---|---|
| `ok` | Connected to the feeder, heartbeat fresh. | A quiet sky is still ready: plane counts don't matter. |
| `feed_disconnected` | The ingest runs but can't connect to `ADSB_HOST:ADSB_PORT`. | The feeder checks below. |
| `stale`, `down` | The ingest isn't heartbeating. | `docker compose logs backend` for its errors. |
| `unknown` | Redis is down (`checks.redis` is `down`). | `docker compose logs redis`. |

**Is the feeder serving SBS?** On the feeder's machine, either command should print lines starting with `MSG,`:

```bash
nc localhost 30003 | head -5                  # install netcat-openbsd if nc is missing
timeout 5 bash -c 'exec 3<>/dev/tcp/localhost/30003; head -5 <&3'
```

If nothing arrives, enable the feeder's SBS output (port 30003) in its settings.

**Can the backend container reach it?**

```bash
docker compose exec backend timeout 5 bash -c 'exec 3<>/dev/tcp/$ADSB_HOST/${ADSB_PORT:-30003} && head -3 <&3'
```

If the host sees SBS lines but the container doesn't:
- For a feeder in a container, the backend has to join its network; see [A feeder in Docker](#a-feeder-in-docker).
- The feeder may listen on 127.0.0.1 only. `ss -ltn 'sport = :30003'` should show `0.0.0.0:30003` or `*:30003`.
- A firewall (ufw, firewalld) may block Docker's bridge from reaching the host.

**Other symptoms:**
- **Ready, but the map stays empty:** `CENTER_LAT` / `CENTER_LON` are probably wrong. Planes farther than `MAX_ANTENNA_RANGE_KM` from the centre are dropped.
- **Planes show, but none offers a round:** no plane has a known route yet. See [Route data](#route-data).
  - The backend log says why: `AeroAPI board refresh is off (<reason>)`, or `Invalid AeroAPI enrichment config, enrichment stays off`.
  - With a key, it logs one line per AeroAPI request. Routes appear about 15 seconds after the first player joins.
- **`docker compose up` fails with `address already in use` or `port is already allocated`:** something else holds `HTTP_PORT`. Pick another port.
- **`docker compose up` warns about memory limit support:** Raspberry Pi OS disables the kernel's memory cgroup, so Docker ignores the containers' memory caps. The game runs fine without them. To enforce them, add ` cgroup_enable=memory cgroup_memory=1` to the end of the single line in `/boot/firmware/cmdline.txt`, and reboot.
- **`docker compose up -d` says the backend is unhealthy, or `/readyz` answers 502:** the API isn't starting, and `docker compose logs backend` shows why.
  - Most invalid settings in `.env` stop it at startup with a validation error naming the setting, for example a lowercase `MONITORED_AIRPORT_ICAO`.
  - Invalid AeroAPI settings and `FAKE_ADSB` don't stop it. They log `Invalid AeroAPI enrichment config`, keep AeroAPI off, and an invalid `FAKE_ADSB` means live mode.

## Known limitations

- **Live rounds need a FlightAware AeroAPI key,** because AeroAPI is the only route source.
- **One airport per instance:** rounds are about `MONITORED_AIRPORT_ICAO` only.
