---
description: Draft a well-structured GitHub issue from a bug report or feature idea
allowed-tools: Bash(gh:*), Read, Glob, Grep
---

# Draft Issue

Draft a GitHub issue with proper structure and acceptance criteria.

**Usage**: `/po-draft-issue <description of bug or feature>`

**Example**: `/po-draft-issue Distance mode freezes after submitting a guess`

## Process

### 1. Determine Issue Type
Based on the description, classify as:
- **Bug**: Something is broken or behaving unexpectedly
- **Feature**: New functionality or enhancement
- **Tech Debt**: Refactoring, cleanup, or infrastructure improvement

### 2. Gather Context
- Search codebase for related files: !`glob pattern for relevant code`
- Check existing issues: !`gh issue list --state all --search "<keywords>"`
- Read PRD for product context: `docs/PRD.md`

### 3. Identify Affected Areas
- Backend: `backend/` - API routes, services, ingest
- Frontend: `frontend/` - Components, hooks, state
- Infrastructure: `infra/` - Docker, deployment

### 4. Draft the Issue

**For Bugs:**
```markdown
## Description
[Clear description of the bug]

## Steps to Reproduce
1. [Step 1]
2. [Step 2]
3. [See error]

## Expected Behavior
[What should happen]

## Actual Behavior
[What actually happens]

## Technical Investigation
- **Likely files**: [list files]
- **Root cause hypothesis**: [your analysis]

## Acceptance Criteria
- [ ] Bug no longer reproduces
- [ ] Regression test added
- [ ] No new bugs introduced

## Severity
[Critical/High/Medium/Low]
```

**For Features:**
```markdown
## Description
As a [user type], I want to [action] so that [benefit].

## Acceptance Criteria
- [ ] [Criterion 1]
- [ ] [Criterion 2]
- [ ] Unit tests added
- [ ] Integration test covers main path
- [ ] Documentation updated (if applicable)

## Technical Approach
- Backend: [changes needed]
- Frontend: [changes needed]
- WebSocket: [if applicable]

## Testing Strategy
- Unit tests: [what to test]
- Integration tests: [what to test]
- Manual testing: [steps]

## Priority
[P0-Critical/P1-High/P2-Medium/P3-Low]
```

### 5. Review Checklist
Before creating the issue, verify:
- [ ] Clear, actionable title
- [ ] Acceptance criteria are testable
- [ ] No duplicate of existing issue
- [ ] Appropriate scope (can be completed in 1-3 days)
- [ ] Aligned with PRD spirit

### 6. Output
Present the drafted issue for review before creating with `/po-create-issue`.
