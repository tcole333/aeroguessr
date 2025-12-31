---
name: workflow-coordination
description: Coordinates multi-agent development workflow with GitHub integration. Auto-activates when orchestrating work across product-owner, developer, and QA agents, or when managing the task selection → implementation → review → merge cycle.
---

# Workflow Coordination

## The Workflow Pattern

This project uses a coordinated multi-agent workflow where the primary chat orchestrates specialized agents:

```
Primary Chat (Orchestrator)
    │
    ├─→ Product Owner Agent
    │   └─→ Creates/selects issues with acceptance criteria
    │
    ├─→ Developer Agent
    │   └─→ Posts plan to issue, implements, opens PR
    │
    └─→ QA Agent
        └─→ Reviews PR, posts feedback, approves/requests changes
```

## Key Principles

### 1. Context Preservation
The primary chat maintains high-level context:
- Current workflow phase
- Active issue/PR numbers
- Decisions made during iteration

Agents work on focused tasks and return summaries.

### 2. GitHub as State Store
All detailed artifacts go to GitHub:
- Implementation plans → Issue comments
- Review feedback → PR reviews
- Discussion → PR comments

This persists context across sessions.

### 3. Clear Handoffs
Each agent returns a structured handoff:
- **Product Owner**: Issue number + summary
- **Developer**: PR number + implementation summary
- **QA**: Review status (approved/changes_requested) + findings

## Dispatching Agents

### Product Owner Agent
```
Task tool with subagent_type "general-purpose":
"Acting as a product-owner for plane-game-v4:
1. Check open issues: gh issue list --state open
2. Identify highest priority ready for development
3. Ensure issue has clear acceptance criteria
4. Return: issue number, title, priority, readiness assessment"
```

### Developer Agent
```
Task tool with subagent_type "general-purpose":
"Acting as a developer for plane-game-v4:
1. Read issue #N: gh issue view N
2. Post implementation plan as issue comment
3. Create branch and implement with tests
4. Run pre-commit and tests
5. Open PR: gh pr create
Return: PR number, files changed, test results"
```

### QA Agent
```
Task tool with subagent_type "general-purpose":
"Acting as QA for plane-game-v4:
1. Review PR #N: gh pr view N, gh pr diff N
2. Check acceptance criteria from linked issue
3. Verify tests are adequate
4. Post review: gh pr review N --approve/--request-changes
Return: review status, key findings, next steps"
```

## Workflow Commands

| Command | Purpose |
|---------|---------|
| `/workflow` | Start full workflow from task selection |
| `/workflow implement <issue>` | Jump to implementation |
| `/workflow review <pr>` | Jump to review |
| `/po-draft-issue` | Draft a new issue |
| `/dev-create-pr` | Create PR with template |
| `/qa-pr-review <pr>` | Review a PR |

## Iteration Pattern

When QA requests changes:
1. Summarize feedback in primary chat
2. Ask user if they want to dispatch developer
3. Developer addresses specific feedback
4. Re-dispatch QA for re-review
5. Repeat until approved

## Merge and Continue

After approval:
```bash
gh pr merge <number> --squash --delete-branch
```

Then ask user if they want to continue with next task.
