---
description: Create a pull request with proper formatting for this project
allowed-tools: Bash(git:*), Bash(gh:*), Bash(poetry:*), Bash(npm:*), Bash(make:*)
---

# Create Pull Request

Create a well-formatted pull request following project conventions.

**Usage**: `/dev-create-pr`

## Prerequisites

Before creating a PR, ensure:
- [ ] All commits pushed to feature branch
- [ ] Tests pass locally
- [ ] Pre-commit hooks pass
- [ ] Issue acceptance criteria met

## Process

### 1. Verify Local State
```bash
# Check current branch
git branch --show-current

# Ensure all changes committed
git status

# Run pre-commit hooks
pre-commit run --all-files
```

### 2. Run Tests
```bash
# Backend unit tests
poetry run pytest tests/backend -m "not integration"

# Frontend tests (if changes)
cd frontend && npm run test:ci && cd ..

# Build check
cd frontend && npm run build && cd ..
```

### 3. Regenerate Schemas (if API/WS changes)
```bash
# If REST API changed
make openapi

# If WebSocket messages changed
make ws-schema
```

### 4. Push Changes
```bash
git push -u origin $(git branch --show-current)
```

### 5. Create PR
```bash
gh pr create \
  --title "<type>: <description> (#<issue>)" \
  --body "$(cat <<'EOF'
Closes #<issue-number>

## Summary
[Brief description of what this PR does and why]

## Changes
- [Change 1]
- [Change 2]
- [Change 3]

## Testing
- [ ] Unit tests pass (`poetry run pytest tests/backend -m "not integration"`)
- [ ] Frontend tests pass (`cd frontend && npm run test:ci`)
- [ ] Pre-commit hooks pass (`pre-commit run --all-files`)
- [ ] Manual testing: [describe what you tested]

## Acceptance Criteria
[Copy from issue and check off]
- [ ] [Criterion 1]
- [ ] [Criterion 2]

## Clean PR Checklist
- [ ] All existing tests still pass
- [ ] No new lint warnings
- [ ] No debug code left in
- [ ] No commented-out code
- [ ] Schemas regenerated if API/WS changed

## Screenshots/Demos
[If UI changes, include screenshots]

## Notes
[Any design decisions, trade-offs, or follow-up items]
EOF
)"
```

### 6. Title Conventions

Match conventional commit format:
- `feat: Add plane type icons (#42)` - New feature
- `fix: Resolve distance mode freeze (#107)` - Bug fix
- `chore: Improve deployment pipeline (#108)` - Maintenance
- `docs: Update enrichment documentation (#109)` - Docs
- `refactor: Extract Kalman filter to module (#110)` - Refactor

### 7. After Creating PR

1. **Verify CI runs**: `gh pr view --web`
2. **Self-review**: Check the diff for debug code, console.logs, etc.
3. **Wait for CI**: Ensure all checks pass before requesting review

## Common Issues

**Pre-commit failing:**
```bash
pre-commit run --all-files
# Fix issues and commit
git add . && git commit --amend
```

**Tests failing:**
```bash
# Run specific test for debugging
poetry run pytest tests/backend/path/to/test.py -v
```

**Merge conflicts:**
```bash
git pull --rebase origin main
# Fix conflicts
git push --force-with-lease
```
