---
description: Create a feature branch from an issue number
allowed-tools: Bash(git:*), Bash(gh:*)
---

# New Branch

Create a properly named feature branch from a GitHub issue.

**Usage**: `/new-branch <issue-number> [slug]`

**Examples**:
- `/new-branch 42` - Auto-generates slug from issue title
- `/new-branch 42 fix-plane-icons` - Uses custom slug

## Process

### 1. Fetch Issue Details
```bash
gh issue view <issue-number> --json title,labels
```

### 2. Determine Branch Type
Based on labels:
- `bug` → `fix/`
- `enhancement` → `feature/`
- `tech-debt` → `chore/`
- `docs` → `docs/`
- Default → `feature/`

### 3. Generate Branch Name
Format: `<type>/<issue>-<slug>`

Examples:
- `feature/42-add-plane-icons`
- `fix/107-plane-movement-jitter`
- `chore/108-deployment-pipeline`

### 4. Create Branch
```bash
# Ensure on main and up to date
git checkout main
git pull origin main

# Create and checkout new branch
git checkout -b <branch-name>
```

### 5. Output
```
Created branch: feature/42-add-plane-icons
From issue: #42 - Add different icons for aircraft types

Next steps:
1. Implement the feature
2. Commit changes: git commit -m "feat: add plane icons (#42)"
3. Push branch: git push -u origin feature/42-add-plane-icons
4. Create PR: /dev-create-pr
```

## Naming Conventions

**Branch prefixes:**
- `feature/` - New functionality
- `fix/` - Bug fixes
- `chore/` - Maintenance, refactoring
- `docs/` - Documentation updates

**Slug rules:**
- Lowercase
- Hyphens instead of spaces
- Short but descriptive (3-5 words max)
- No special characters
