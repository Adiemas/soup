---
name: using-git-worktrees
description: Use when starting feature work that needs isolation from the current workspace, or before executing an implementation plan. Creates per-feature worktrees under .soup/worktrees/.
---

# Using Git Worktrees

## Overview
Per-feature isolation. A worktree is a second checkout of the same repo in a separate directory, sharing history. Plans execute in worktrees so the main workspace stays clean and concurrent features can't collide.

## Iron Law
```
EVERY /implement RUN HAPPENS IN A DEDICATED WORKTREE UNDER .soup/worktrees/. MAIN IS NEVER DIRECTLY EDITED.
```

## Process

1. **Name the worktree** after the feature/spec: `.soup/worktrees/<slug>`. Slug matches the spec filename.
2. **Create a branch for it.** Conventional: `feat/<slug>` or `fix/<slug>`.
3. **Create the worktree:**
   ```
   git worktree add .soup/worktrees/<slug> -b feat/<slug>
   ```
4. **Verify isolation.** `git worktree list` shows the new path. Main has no uncommitted changes tied to this feature.
5. **Run the plan inside the worktree.** All orchestrator commits land on `feat/<slug>`.
6. **On completion + QA APPROVE,** open a PR from `feat/<slug>` via `github-agent` or `ado-agent`.
7. **After merge,** remove the worktree:
   ```
   git worktree remove .soup/worktrees/<slug>
   git branch -d feat/<slug>
   ```
8. **On BLOCK or abandonment,** Constitution IX.3: discard the worktree and re-plan. Never partially-merge.

## Red Flags

| Thought | Reality |
|---|---|
| "Just edit in main, it's a small change." | Small changes deserve clean history too. Worktree. |
| "Two features in one worktree — related anyway." | Related ≠ same unit of work. Separate worktrees, separate PRs. |
| "Force-removing a worktree to skip cleanup." | Use `git worktree remove` + branch delete. Force-delete loses work silently. |
| "Broken worktree — let me commit a partial fix to save progress." | Constitution IX.3: discard, re-plan. Do not pollute history. |
| "I'll share the worktree between two agents — save disk." | Concurrent edits race. One worktree per execution. |

## Related skills
- `executing-plans` — runs in a worktree
- `finishing-a-development-branch` — decides worktree fate at end
- `dispatching-parallel-agents` — parallel features use separate worktrees
