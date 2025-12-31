---
description: Review a pull request with full context gathering
allowed-tools: Bash(gh:*), Bash(git:*), Read, Glob, Grep
---

# PR Review

Gather context and review a pull request thoroughly.

**Usage**: `/qa-pr-review <pr-number>`

**Example**: `/qa-pr-review 50`

## Process

### 1. Fetch PR Details
```bash
gh pr view <pr-number> --json title,body,author,files,commits,comments,reviews,baseRefName,headRefName
```

### 2. Get Related Issue
Extract issue number from PR body (`Closes #N`) and fetch:
```bash
gh issue view <issue-number> --json title,body,labels
```

### 3. Review Changed Files
```bash
gh pr diff <pr-number>
```

### 4. Check CI Status
```bash
gh pr checks <pr-number>
```

### 5. Checkout and Test Locally
```bash
gh pr checkout <pr-number>

# Run tests
poetry run pytest tests/backend -m "not integration"
cd frontend && npm run test:ci && cd ..

# Run pre-commit
pre-commit run --all-files
```

### 6. Review Checklist

**Code Quality:**
- [ ] Code follows project patterns (see `docs/project-standards.md`)
- [ ] No unnecessary complexity
- [ ] Error handling is appropriate
- [ ] No security vulnerabilities (input validation, XSS, etc.)

**Testing:**
- [ ] Tests cover new functionality
- [ ] Tests validate behavior, not implementation
- [ ] Edge cases considered
- [ ] No reward hacking (tests that pass but don't verify behavior)

**This Project Specifics:**
- [ ] WebSocket messages follow schema (`docs/ws_schema.yaml`)
- [ ] REST API matches OpenAPI (`docs/api_openapi.yaml`)
- [ ] Redis keys follow naming convention (`plane:{hex}`, `room:{code}:*`)
- [ ] Frontend uses Zustand store correctly
- [ ] Mobile-first responsive design maintained

**Clean PR:**
- [ ] No debug code (console.log, print statements)
- [ ] No commented-out code
- [ ] No TODO comments without issue references
- [ ] Schemas regenerated if API/WS changed

### 7. Acceptance Criteria Check
Compare PR changes against issue acceptance criteria:
- [ ] Each criterion is addressed
- [ ] Nothing out of scope added
- [ ] No scope creep

### 8. Output Format

```markdown
## PR Review: #<pr-number>

### Summary
- **Title**: <title>
- **Author**: @<author>
- **Issue**: #<issue-number> - <issue-title>
- **CI Status**: [Pass/Fail]

### Files Changed (<count>)
- `path/to/file.py` (+X, -Y)
- ...

### Acceptance Criteria Status
- [x] Criterion 1 - Verified in `file.py:45`
- [ ] Criterion 2 - Not addressed
- [x] Criterion 3 - Verified

### Review Findings

**Approve / Request Changes / Comment**

**Issues Found:**
1. [Critical/Warning/Suggestion] Description in `file.py:line`
2. ...

**Positive Observations:**
- Good test coverage for X
- Clean implementation of Y

### Recommended Actions
1. [If changes requested]
2. [Suggestions for improvement]
```

## After Review

- Add review comment with findings
- Request changes if needed: `gh pr review <pr-number> --request-changes --body "..."`
- Approve if ready: `gh pr review <pr-number> --approve --body "LGTM! ..."`
