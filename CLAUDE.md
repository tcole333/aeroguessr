# Claude Code Developer Guide

Real-time flight guessing game using live ADS-B data. Players join rooms and guess flight origins/destinations.

## Quick Start

```bash
# Start dev environment
make dev

# Or run services separately:
poetry run uvicorn backend.app:app --reload --port 8000
cd frontend && npm run dev
```

## Project Structure

| Directory | Purpose | CLAUDE.md |
|-----------|---------|-----------|
| `backend/` | FastAPI, Redis, WebSockets, ADS-B ingest | [Backend Guide](backend/CLAUDE.md) |
| `frontend/` | React, TypeScript, Leaflet, Zustand | [Frontend Guide](frontend/CLAUDE.md) |
| `infra/` | Docker, Pi deployment | [Infra Guide](infra/CLAUDE.md) |
| `docs/` | PRD, schemas, standards | - |
| `tests/` | Unit + integration tests | - |

## Key Documentation

- **Product**: [docs/PRD.md](docs/PRD.md) - Requirements and gameplay mechanics
- **Standards**: [docs/project-standards.md](docs/project-standards.md) - Coding conventions
- **API Schema**: [docs/api_openapi.yaml](docs/api_openapi.yaml) - Auto-generated
- **WS Schema**: [docs/ws_schema.yaml](docs/ws_schema.yaml) - Auto-generated
- **Tech Debt**: [TECH_DEBT.md](TECH_DEBT.md) - Known issues and improvements

## Slash Commands

### Issue Management
| Command | Description |
|---------|-------------|
| `/po-draft-issue <description>` | Draft a well-structured GitHub issue |
| `/po-create-issue` | Create issue in GitHub from draft |
| `/issue [number]` | Workflow to work on an issue |
| `/create <description>` | Review and create an issue |

### Development Workflow
| Command | Description |
|---------|-------------|
| `/workflow` | **Full orchestrated workflow** - task selection → implementation → review |
| `/new-branch <issue> [slug]` | Create feature branch from issue |
| `/dev-create-pr` | Create PR with proper formatting |
| `/qa-pr-review <pr-number>` | Review a PR with context |

### Utilities
| Command | Description |
|---------|-------------|
| `/document` | Documentation audit |

## Agents

Custom agents in `.claude/agents/`:
- **developer** - Feature implementation, bug fixes
- **qa** - PR review, quality checks
- **devops** - Deployment, infrastructure
- **product-owner** - Issue creation, prioritization

## Development Workflow

### Coordinated Multi-Agent Workflow

Use `/workflow` for the full orchestrated cycle:

```
/workflow
    │
    ├─→ Product Owner Agent selects/creates issue
    │   └─→ Returns: Issue #N ready for development
    │
    ├─→ Developer Agent implements
    │   ├─→ Posts plan to issue comment
    │   ├─→ Creates branch, implements, tests
    │   └─→ Returns: PR #M opened
    │
    └─→ QA Agent reviews
        ├─→ Posts review to PR
        └─→ Returns: approved / changes_requested
            │
            └─→ If changes needed: iterate with developer
```

### Quick Manual Workflow

```bash
# 1. Check for issues
gh issue list --state open

# 2. Create branch
/new-branch <issue-number>

# 3. Implement (with tests)
poetry run pytest tests/backend -m "not integration"
cd frontend && npm run test:ci

# 4. Pre-commit checks
pre-commit run --all-files

# 5. Create PR
/dev-create-pr
```

## Common Commands

```bash
# Testing
poetry run pytest tests/backend -m "not integration"  # Backend
cd frontend && npm run test:ci                        # Frontend
make integration-test                                 # Full integration

# Linting
pre-commit run --all-files

# Schema updates
make openapi     # REST API
make ws-schema   # WebSocket

# Fake ADS-B data
FAKE_ADSB=1 poetry run python -m backend.ingest.main
```

## Environment Setup

```bash
# Backend
poetry install --with dev

# Frontend
cd frontend && npm install

# Pre-commit hooks
pre-commit install

# Environment
cp .env.example .env
```

## GitHub

- **Repo**: https://github.com/tcole333/plane-game-v4
- **Issues**: https://github.com/tcole333/plane-game-v4/issues
- **Issue Templates**: `.github/ISSUE_TEMPLATE/` (bug, feature, tech-debt)

## Pi Deployment

Target: Raspberry Pi 4 at 192.168.1.181 (`ssh pi-plane`)

See [infra/CLAUDE.md](infra/CLAUDE.md) for deployment details.

### Pull-Based Auto-Deployment

The Pi polls GitHub every 1 minute and auto-deploys changes. No GitHub Actions or GHCR images needed - builds happen natively on the Pi for faster ARM64 compilation (~3-5 min vs 30+ min with QEMU).

```bash
# Just push to main - Pi will auto-deploy within 1 minute
git push origin main

# Monitor deployment on Pi
ssh pi-plane "tail -f /home/pi/plane-game-v4/logs/auto-update.log"

# Trigger immediate deployment
ssh pi-plane "/home/pi/plane-game-v4/scripts/auto-update.sh"

# Check timer status
ssh pi-plane "systemctl status plane-game-update.timer"
```

### Manual Deployment (Fallback)

```bash
ssh pi-plane
cd /home/pi/plane-game-v4
git pull origin main
docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml build
docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml up -d
```

---

**Workflow**: Issue → Branch → Implement → Test → PR → Review → Merge
