---
description: Create a GitHub issue from a drafted issue
allowed-tools: Bash(gh:*)
---

# Create Issue

Create a GitHub issue from a previously drafted issue.

**Usage**: `/po-create-issue`

**Prerequisites**:
- Issue has been drafted with `/po-draft-issue`
- Draft has been reviewed and approved

## Process

### 1. Confirm Issue Details
Review the drafted issue content and confirm:
- Title follows conventions
- Labels are appropriate
- Acceptance criteria are complete

### 2. Create the Issue

**For Bugs:**
```bash
gh issue create \
  --title "fix: <description>" \
  --label "bug" \
  --label "<severity>" \
  --body "$(cat <<'EOF'
## Description
[Description from draft]

## Steps to Reproduce
[Steps from draft]

## Expected Behavior
[Expected from draft]

## Actual Behavior
[Actual from draft]

## Technical Investigation
[Investigation from draft]

## Acceptance Criteria
[Criteria from draft]
EOF
)"
```

**For Features:**
```bash
gh issue create \
  --title "feat: <description>" \
  --label "enhancement" \
  --label "<priority>" \
  --body "$(cat <<'EOF'
## Description
[Description from draft]

## Acceptance Criteria
[Criteria from draft]

## Technical Approach
[Approach from draft]

## Testing Strategy
[Strategy from draft]
EOF
)"
```

**For Tech Debt:**
```bash
gh issue create \
  --title "chore: <description>" \
  --label "tech-debt" \
  --label "<priority>" \
  --body "$(cat <<'EOF'
## Description
[Description from draft]

## Current Problems
[Problems from draft]

## Proposed Solution
[Solution from draft]

## Acceptance Criteria
[Criteria from draft]
EOF
)"
```

### 3. Title Conventions
- `feat: Add presigned URL endpoint` - New feature
- `fix: Prevent auth token refresh loop` - Bug fix
- `chore: Update dependencies` - Maintenance
- `docs: Add API documentation` - Documentation
- `refactor: Extract S3 helpers` - Code improvement

### 4. Labels to Apply
**Type:**
- `bug` / `enhancement` / `tech-debt` / `docs`

**Area:**
- `backend` / `frontend` / `infra`

**Priority:**
- `P0-critical` / `P1-high` / `P2-medium` / `P3-low`

### 5. After Creation
1. Note the issue number returned
2. Update any tracking documents (e.g., plan files)
3. Optionally assign to a milestone
