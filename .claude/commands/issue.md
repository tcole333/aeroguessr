---
description: Workflow to select and work on an issue
allowed-tools: Bash(gh:*), Bash(git:*), Bash(make:*)
---

# Issue Workflow

Please review CLAUDE.md, README.md, and docs/project-standards.md, then follow the workflow to select the next issue to work on.

## Steps:

### 1. **Select an issue**:
- **If issue provided**: Work on issue: $ARGUMENTS
- **If no issue provided**: Check open issues and choose based on priority or relevance
  - Available open issues: !`gh issue list --state open --limit 10`

### 2. **Understand the issue**:
Read the full description, acceptance criteria, and any linked context

### 3. **Investigate the codebase**:
Locate relevant code, components, tests, and dependencies

### 4. **Use TodoWrite**:
Create a task list to track your implementation progress

### 5. **Plan your approach**:
- Identify potential challenges and edge cases
- Check for related issues or dependencies
- Consider mobile-first and performance implications
- Plan the testing strategy

### 6. **Implement the solution**:
- Follow coding standards from project-standards.md
- Address the root cause, not just symptoms
- Keep changes focused on the issue scope

### 7. **Add comprehensive tests**:
- Unit tests with >80% coverage
- Integration tests for main paths
- Manual testing on different devices

### 8. **Update documentation**:
- Regenerate schemas if needed (make openapi/ws-schema)
- Update relevant docs
- Comment on the issue with progress

### 9. **Final review checklist**:
- All tests passing
- Pre-commit hooks pass
- No console errors/warnings
- Mobile responsive
- Accessibility checked

### 10. **Raise PR**:
Follow the PR template and reference the issue

## Remember:
Use existing workflows in CLAUDE.md for branch creation, commits, and PR process.
