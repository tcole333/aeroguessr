---
description: Orchestrate the full development workflow - from task selection through PR merge
allowed-tools: Bash(gh:*), Task, Read, TodoWrite
---

# Development Workflow Orchestration

This command orchestrates the full development cycle, dispatching specialized agents for each phase while maintaining context in the primary chat.

**Usage**: `/workflow [action]`

**Actions**:
- `/workflow` or `/workflow next` - Start with task selection
- `/workflow implement <issue>` - Skip to implementation phase
- `/workflow review <pr>` - Skip to review phase
- `/workflow status` - Show current workflow state

## Workflow Phases

```
┌─────────────────────────────────────────────────────────────────┐
│                     PRIMARY CHAT (You are here)                 │
│                     Orchestrates and maintains context          │
└──────────────────────────────┬──────────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌───────────────┐    ┌─────────────────┐    ┌────────────────┐
│ Product Owner │    │   Developer     │    │   QA/Testing   │
│    Agent      │    │     Agent       │    │     Agent      │
├───────────────┤    ├─────────────────┤    ├────────────────┤
│ • Select task │    │ • Write plan    │    │ • Review PR    │
│ • Create issue│    │ • Implement     │    │ • Test changes │
│ • Prioritize  │    │ • Open PR       │    │ • Give feedback│
└───────────────┘    └─────────────────┘    └────────────────┘
        │                      │                      │
        └──────────────────────┴──────────────────────┘
                               │
                    GitHub Issues & PRs
                    (Persistent State)
```

## Phase 1: Task Selection (Product Owner)

Dispatch the product-owner agent to:
1. Review open issues and priorities
2. Select the next task to work on
3. Create new issues if needed (from bug reports, feature ideas)
4. Ensure issue has clear acceptance criteria

```
Use Task tool with product-owner agent:
"Review open issues at github.com/tcole333/plane-game-v4.
 Identify the highest priority issue that's ready for development.
 If the issue lacks acceptance criteria, add them.
 Return the issue number and a summary."
```

**Output**: Issue number and summary ready for development.

## Phase 2: Implementation (Developer)

Dispatch the developer agent to:
1. Read the issue thoroughly
2. Write a detailed implementation plan as a comment on the issue
3. Create feature branch
4. Implement the solution with tests
5. Open a PR referencing the issue

```
Use Task tool with developer agent:
"Implement issue #<number> for the plane-game-v4 project.

 Steps:
 1. Read the issue and understand requirements
 2. Post your implementation plan as a comment on the issue
 3. Create branch: git checkout -b fix/<number>-<slug>
 4. Implement with tests
 5. Run: pre-commit run --all-files
 6. Run: poetry run pytest tests/backend -m 'not integration'
 7. Create PR with: gh pr create --title '...' --body 'Closes #<number>...'

 Return the PR number when complete."
```

**Output**: PR number ready for review.

## Phase 3: Review (QA Agent)

Dispatch the QA agent to:
1. Review the PR diff
2. Check against acceptance criteria
3. Verify tests are adequate
4. Post review comments on the PR
5. Request changes or approve

```
Use Task tool with qa agent:
"Review PR #<number> for the plane-game-v4 project.

 Steps:
 1. Fetch PR details: gh pr view <number> --json title,body,files
 2. Get the linked issue and its acceptance criteria
 3. Review the diff: gh pr diff <number>
 4. Check CI status: gh pr checks <number>
 5. Post your review: gh pr review <number> --comment --body '...'
 6. If issues found, request changes with specific feedback
 7. If ready, approve: gh pr review <number> --approve

 Return: approved, changes_requested, or needs_discussion"
```

**Output**: Review status and any required changes.

## Phase 4: Iteration (if needed)

If QA requests changes:
1. Summarize the feedback in primary chat
2. Dispatch developer agent to address feedback
3. Re-dispatch QA agent after fixes
4. Repeat until approved

## Phase 5: Merge

Once approved:
```bash
gh pr merge <number> --squash --delete-branch
```

Then return to Phase 1 for the next task.

## Maintaining Context

The primary chat maintains:
- Current workflow phase
- Active issue/PR numbers
- Summary of agent outputs
- Decisions made during iteration

Agents receive:
- Specific task instructions
- Issue/PR numbers to work with
- Clear success criteria

GitHub stores:
- Detailed plans (issue comments)
- Review feedback (PR comments)
- Implementation history (commits)

## Example Session

```
User: /workflow

Claude: I'll start the development workflow. Let me dispatch the product-owner
        agent to identify the next task...

        [Dispatches product-owner agent]

        Product Owner identified Issue #107 (Plane movement jitter) as highest
        priority. The issue has clear acceptance criteria. Ready for development.

        Shall I dispatch the developer agent to implement this?

User: yes

Claude: [Dispatches developer agent with issue #107]

        Developer agent has:
        - Posted implementation plan to issue #107
        - Created branch fix/107-plane-jitter
        - Implemented Kalman filter fixes
        - Added tests
        - Opened PR #112

        Ready for QA review. Shall I dispatch the QA agent?

User: yes

Claude: [Dispatches QA agent with PR #112]

        QA Review complete:
        - Acceptance criteria: 4/5 met
        - Missing: Frontend interpolation test
        - Posted review requesting changes

        Developer needs to add the missing test. Dispatch developer to fix?

User: yes

Claude: [Dispatches developer agent to address feedback]

        Developer has:
        - Added frontend interpolation test
        - Pushed to PR #112

        Re-running QA review...

        [Dispatches QA agent]

        QA approved! Ready to merge?

User: merge it

Claude: gh pr merge 112 --squash --delete-branch
        ✓ PR #112 merged

        Ready for next task. Run /workflow to continue.
```

## Quick Commands

For experienced users who want to skip phases:

```bash
# Jump straight to implementing a specific issue
/workflow implement 107

# Jump straight to reviewing a specific PR
/workflow review 112

# Check current workflow state
/workflow status
```
