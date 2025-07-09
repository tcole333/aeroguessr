# Claude Code Developer Guide

This guide helps Claude Code work effectively on the Plane Game v4 codebase. For detailed project documentation, see @README.md and @docs/

## 🎯 Current Work

**Last Updated:** [Claude will update this]

### Active Development
- **Current Branch:** [branch name]
- **Current Issue:** #[number] - [description]
- **Status:** [e.g., "implementing websocket handler", "writing tests"]

### Check for New Work
```bash
# View assigned issues
gh issue list --state open --assignee @me

# View all open issues
gh issue list --state open
```

GitHub Issues: https://github.com/tcole333/plane-game-v4/issues

## 🚀 Development Workflow

### 1. Starting New Work
```bash
# Always start from main
git checkout main && git pull

# Create feature branch for issue #N
git checkout -b feature/N-short-description

# Or use the helper script
./scripts/new-feature.sh N
```

### 2. Development Cycle
```bash
# Before ANY commit - run pre-commit hooks
pre-commit run --all-files

# Quick validation based on what changed
./scripts/pre-flight.sh  # (once created)

# Manual checks if needed:
# - Backend: poetry run pytest tests/backend -m "not integration"
# - Frontend: cd frontend && npm run test:ci && npm run build
```

### 3. Creating PRs
```bash
# Create draft PR
gh pr create --title "feat: Short description" \
             --body "Closes #N\n\n## Changes\n- Change 1\n- Change 2" \
             --draft

# After CI passes, mark ready
gh pr ready
```

### 4. Before Merging
- All CI checks must pass
- Update any generated files:
  - API changes: `make openapi`
  - WebSocket changes: `make ws-schema`

### 5. Creating new issues for features and bugs
- Use the issue templates in @docs/ISSUE_TEMPLATE/
- There are separate ones for features, bugs and tech-debt depending on the issue to be raised
- Features should be small and self contained to allow for iterative development
```bash
gh issue create --title "Test feature for script" --body "Testing the new-feature script"
```

## 📋 Quick Reference

### Project Structure
- **Backend**: `backend/` - FastAPI, Redis, WebSockets
- **Frontend**: `frontend/` - React, TypeScript, Vite, Leaflet
- **Tests**: `tests/` - Unit tests (fast) + Integration tests (slower)
- **Docs**: `docs/` - PRD, standards, schemas, ADRs
- **Logs**: `logs/` - logging for the app
- **Infra**: `infra/` - infra for the app, docker images etc.
- **Scripts**: `scripts/` - helper scripts for workflow

### Key Documentation
- @docs/PRD.md
- @docs/project-standards.md - **Read Section 1 for LLM rules**
- @docs/api_openapi.yaml - Auto-generated
- @docs/ws_schema.yaml - Auto-generated
- @TECH_DEBT.md

### Common Commands
```bash
# Run the dev environment
make dev

# Backend only (faster iteration)
poetry run uvicorn backend.app:app --reload --port 8000

# Start data ingestion with fake ADS-B data
export FAKE_ADSB=1
export FAKE_ADSB_FILE=synthetic
poetry run python -m backend.ingest.main


# Testing
poetry run pytest tests/backend -m "not integration"  # Fast unit tests
make integration-test  # Full integration tests

# Linting/Formatting
pre-commit run --all-files
ruff check . && ruff format .

# Update schemas after API changes
make openapi
make ws-schema
```

## 🤝 Session Handoff

**Session Date:** [date]

### Work Completed
- [x] Completed task
- [ ] Partially complete task

### Current State
- **Branch:** [branch name]
- **Uncommitted changes:** [yes/no - describe if yes]
- **Tests passing:** [yes/no - which failing if no]
- **Blockers:** [any blocking issues]

### Next Session Should
1. [Specific next action]
2. [Another action]

### Notes/Warnings
- [Any gotchas or important context]

## 🛠 Helper Scripts (To Be Created)

### `scripts/new-feature.sh`
Creates branch from issue number, pulls issue title for branch name


## ⚡ Development Tips

1. **Commit Messages**: Use conventional commits (feat:, fix:, docs:, etc.)
2. **Testing**: Unit tests on every commit, integration tests before merge
3. **Documentation**: Update docs with code changes, especially:
   - API changes → regenerate OpenAPI
   - New features → update PRD
   - Architecture changes → update ADR
   - TODOs → add to TECH_DEBT.md

4. **Branch Hygiene**: Keep branches small and focused on one issue

## 🔧 Environment Setup

Required tools:
- Python 3.12+ with Poetry
- Node.js & npm (frontend)
- Docker & Docker Compose
- Git with GitHub CLI (`gh`)

First time setup:
```bash
# Backend
poetry install --with dev

# Frontend
cd frontend && npm install

# Pre-commit hooks
pre-commit install

# Environment variables
cp .env.example .env
# Edit .env with your values
```

## Known Issues & Workarounds

[Track any persistent issues or quirks here]

---

**Remember**: Each issue = new branch = new PR. Keep changes small and focused!
