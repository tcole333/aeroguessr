# Claude Code Developer Guide

This guide helps Claude Code work effectively on the Plane Game v4 codebase. For detailed project documentation, see @README.md and @docs/

## 🎯 Current Work

**Last Updated:** 2025-07-11

### Active Development
- **Current Branch:** feature/73-airport-autocomplete-component
- **Current Issue:** #73 - Create airport autocomplete React component
- **Status:** Implementation complete, PR ready to be created

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

# Review important docs like CLAUDE.md, READMEs, project-standards

# Fetch issues to view open items
gh issue list --state open --assignee @me
# Or view all issues
gh issue list --state all

# Decide on the next issue to work on
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

# Commit changes
git add .
git commit -m "feat: descriptive commit message"

# Push changes (first time)
git push -u origin feature/N-branch-name
# Or for subsequent pushes
git push
```

### 3. Update documentation
- Documentation should be updated after development is completed and tests are passing
- Be sure to regenerate any of the type files or api docs if needed
- Update the issue in github to reflect the updates and new status

### 4. Creating PRs
```bash
# Create draft PR
gh pr create --title "feat: Short description" \
             --body "Closes #N\n\n## Changes\n- Change 1\n- Change 2" \
             --draft

# After CI passes, mark ready
gh pr ready
```

### 5. Before Merging
- All CI checks must pass
- Update any generated files:
  - API changes: `make openapi`
  - WebSocket changes: `make ws-schema`
- Ensure PR has been reviewed (see section 6 for review checklist)
- Rebase or squash commits if needed for clean history


### 6. PR Review & Merge Process
```bash
# Check for open PRs
gh pr list --state open

# Review specific PR
gh pr view 42  # View PR details
gh pr diff 42  # View changes

# Checkout PR for local testing
gh pr checkout 42
```

#### PR Review Checklist
- [ ] **Issue Reference**: PR description references the correct issue (`Closes #N`)
- [ ] **Code Quality**:
  - Follows project standards (@docs/project-standards.md)
  - Has appropriate tests (unit/integration)
  - Includes proper error handling
  - Functions are documented with docstrings
- [ ] **CI Status**: All GitHub Actions checks pass
- [ ] **Documentation**:
  - API changes have updated OpenAPI (`make openapi`)
  - WebSocket changes have updated schema (`make ws-schema`)
  - README updated if needed
- [ ] **Testing**:
  - Unit tests pass: `poetry run pytest tests/backend -m "not integration"`
  - Frontend tests pass: `cd frontend && npm run test:ci`
  - Integration tests pass: `make integration-test`
- [ ] **Manual Testing**: Feature works as expected in local environment
- [ ] **Follow-up Issues**: Identify and create issues for improvements that shouldn't block merge
- [ ] **Documentation Updates**: Update TECH_DEBT.md and session handoff notes

#### Creating Follow-up Issues During Review
**When to create follow-up issues:**
- Performance optimizations identified but not critical
- Code refactoring opportunities that don't affect functionality
- Enhanced error handling or logging improvements
- UI/UX improvements that aren't core to the current feature
- Technical debt items discovered during review
- Documentation enhancements beyond the current scope

**Guidelines for follow-up issues:**
- Label with appropriate priority (low/medium for most follow-ups)
- Reference the original PR: "Follow-up from PR #42"
- Include specific code references and suggested improvements
- Don't create follow-up issues for critical bugs or security issues (these should block merge)

```bash
# Create follow-up issue from review findings
gh issue create --title "Performance: Optimize WebSocket message compression" \
                --body "Follow-up from PR #42\n\nDuring review, identified opportunity to add permessage-deflate compression to reduce bandwidth usage..." \
                --label "enhancement,performance"

# Merge PR (squash and merge recommended)
gh pr merge 42 --squash --delete-branch

# Close related issue if not auto-closed
gh issue close 32 --comment "Fixed in PR #42"

# Update TECH_DEBT.md to reflect completion
# Update session handoff notes with current status

# Switch back to main and pull latest
git checkout main && git pull
```

### 7. Creating new issues for features and bugs
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

**Session Date:** 2025-07-11

### Work Completed
- [x] Fixed leave room button functionality (Issue #32)
- [x] Added missing WebSocket schema documentation for leave messages
- [x] Implemented complete frontend leave room flow with state cleanup
- [x] Fixed bidirectional ping/pong message type generation
- [x] Added comprehensive tests for leave room functionality
- [x] Resolved console validation errors for ping messages
- [x] Fixed plane trails rendering (Issue #40) - reduced from 30 to 10 points for better performance
- [x] Standardized nick/nickname usage across frontend codebase (Issue #31, PR #50)
- [x] Implemented browser refresh rejoin functionality (Issue #38, PR #51)
- [x] Implemented comprehensive logging system (Issues #35, #36, PR #59)
- [x] Fixed auto-rejoin after intentional leave room action (Issue #52, PR #60)
- [x] Fixed critical Redis WRONGTYPE error preventing plane movement (Issue #58, PR #63)
- [x] Implemented intelligent range-based plane filtering (Issue #58, PR #63)
- [x] Implemented round result modal with scoring feedback (Issue #55, PR #66)
- [x] Added scoring mode indicator with round timer (Issue #56, PR #66)
- [x] Implemented game status and round progress indicators (Issue #57, PR #67)
- [x] Fixed leaderboard real-time updates (Issue #65, PR #69)
- [x] Fixed critical backend host validation bug preventing new hosts from selecting planes (Issue #65, PR #69)
- [x] Prepared frontend-optimized airport dataset (Issue #72, PR #80)
- [x] Created comprehensive airport autocomplete React component (Issue #73)

### Current State
- **Branch:** feature/73-airport-autocomplete-component
- **Uncommitted changes:** None - all changes committed and pushed
- **Tests passing:** Yes - All frontend tests (36 new tests added), Backend tests
- **Blockers:** None - Ready to create PR

### Next Session Should
1. Create PR for airport autocomplete component (Issue #73)
2. Wait for PR #80 review and merge (frontend-optimized airport dataset)
3. Work on integrating autocomplete into game flow (Issue #74) once both PRs are merged
4. Consider fixing the pre-commit hook poetry path issue if needed
5. Review and address integration test failures in TECH_DEBT.md
6. Check for any new high-priority issues

### Notes/Warnings
- **Critical Fix**: Redis WRONGTYPE error resolved - planes now move properly (PR #63)
- **Plane Filtering**: Range-based filtering implemented - stale flights automatically removed (PR #63)
- **Logging system**: All logs now captured to files in `logs/` directory with automatic rotation
- **Frontend logging**: Console logs automatically sent to backend and persisted to `logs/frontend.log`
- **Integration tests**: Logs now saved to `logs/integration.log` instead of `logs.txt`
- **Log rotation**: Development-friendly settings (5MB files, 1 day retention) vs production (daily rotation with compression)
- Browser refresh rejoin functionality now fully implemented with session persistence
- Nickname inconsistencies resolved - removed duplicate playerNickname property
- Frontend connection state now uses single nickname property consistently
- All variable names standardized to use 'nickname' instead of 'nick'
- Backend naming conventions maintained (snake_case for APIs, camelCase for frontend state)
- localStorage key changed from 'plane-ui' to 'plane-session' (may reset user preferences)
- Auto-rejoin issue resolved - users can now properly leave rooms without being reconnected
- **Round Result Modal**: Uses React portal to ensure proper z-index above map elements
- **Score Mode Indicator**: Timer component manages its own interval for countdown functionality
- **Game Status Indicator**: Shows game phase, round number, and countdown timer with progress bar
- **UI Enhancement Trilogy Complete**: Issues #55, #56, and #57 all implemented for comprehensive game feedback
- **WebSocket Auto-Reconnect Fixed**: The WebSocket client now properly distinguishes between intentional disconnections (Leave Room) and unintentional ones (network issues)
- **Host Transfer Fixed**: Backend now uses dynamic host validation instead of stale connection-scoped variables
- **Critical Backend Fix**: Host validation bug prevented new hosts from performing actions - now checks Redis dynamically
- **Airport Dataset**: Frontend-optimized dataset created with ~3K major airports (132KB gzipped) for autocomplete feature
- **Airport Data Generation**: Run `python backend/scripts/populate_airports_data.py` to regenerate both backend and frontend datasets
- **Airport Autocomplete Component**: Comprehensive React component with Fuse.js fuzzy search, full keyboard navigation, accessibility, and mobile optimization
- **Component Features**: Debounced search (150ms), ARIA compliant, dark mode support, <50ms search performance, 36 unit tests
- **Pending Tasks**: Mobile device testing still needed, documentation/usage examples to be created

## 🛠 Helper Scripts

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
- there might be issues with the poetry path in the terminal session, you can use the full path
- like /opt/homebrew/bin/poetry run or try and source the .zprofile to see if it fixes it

[Track any persistent issues or quirks here]

---

**Remember**: Each issue = new branch = new PR. Keep changes small and focused!
