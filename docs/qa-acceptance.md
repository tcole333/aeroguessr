## 0 Project Bootstrap

- [ ] PASS if a LICENSE file declaring MIT is present.
- [ ] PASS if README.md quick-start instructions (docker compose up) bring up:
  - [ ] the backend reachable at GET /healthz → 200, and
  - [ ] the React UI at / within 60 s on the Pi.
- [ ] PASS if .env.example contains all variables listed in PRD § 7.1.
- [ ] PASS if sample_data/ exists with at least:
  - [ ] one 1-minute SBS dump (adsb_1min.sbs), and
  - [ ] a mini airport list (airports_min.json).
- [ ] PASS if ADR/0001-initial.md (first Architecture-Decision Record) and .cursorrules are present.
- [ ] PASS if pre-commit run --all-files exits 0 on a fresh clone.

## 1 Environment & CI

- [ ] FAIL if ruff, black --check, or eslint exit non-zero.
- [ ] FAIL if unit-test coverage drops below 85 % (backend) or 80 % (frontend).
- [ ] PASS if the multi-arch Docker image builds in <3 min on GitHub Actions.

## 2 Flight Ingest Service

- [ ] PASS if the service parses ≥ 99 % of lines in sample_data/adsb_1min.sbs without error.
- [ ] PASS if Redis plane:\* keys appear with valid JSON and expire after 5 ± 1 min.
- [ ] PASS if heading variance between successive points is < 30° RMS post-Kalman.
- [ ] PASS if enrichment cache hit-rate ≥ 90 % when replaying sample_data twice.

## 3 Mock ADS-B Generator

- [ ] Controlled solely by env flag FAKE_ADSB=1 (backend restart toggles).
- [ ] Generates 1–3 aircraft drifting realistically ≤ 10 km from the centre.

## 4 WebSocket Gateway

- [ ] PASS if stateSync arrives within 250 ms of WS connect (LAN).
- [ ] PASS if unplugging the client's network for 15 s, then reconnecting, resumes with the same room_state.version.
- [ ] PASS if roundStart → roundResult runs without dropped messages for 50 simulated players (autocannon test).

## 5 Game Logic

- [ ] Scoring matches spec (exact = 100, distance taper linear).
- [ ] Host disconnect > 2 min triggers newHost invitation; > 5 min triggers auto-assign.
- [ ] Room auto-deletes after 60 ± 5 min inactivity.

## 6 Frontend Mobile UI

- [ ] Loads on iPhone Safari ≤ 400 ms cold start (local static server).
- [ ] Tapping a plane pans/zooms and opens details within one animation frame (~16 ms).
- [ ] Autocomplete returns first suggestion < 100 ms per keystroke on a mid-tier Android.
- [ ] Night-mode toggle persists across reload (localStorage).
- [ ] Lighthouse scores: Performance ≥ 95, Accessibility ≥ 90.

## 7 End-to-End Smoke

- [ ] Cypress script spins up mock ADS-B, creates a room, joins a second player, completes one round; all assertions pass.
