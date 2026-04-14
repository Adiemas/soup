---
name: requesting-code-review
description: Use when completing tasks, implementing major features, or before merging. Two-stage review — spec compliance first, code quality second.
---

# Requesting Code Review

## Overview
Before claiming work is merge-ready, dispatch `code-reviewer` (and the wider `qa-orchestrator` if warranted). The review runs two stages: **spec compliance** first, then **code quality**. An elegant implementation of the wrong spec is still a failure.

## Iron Law
```
SPEC COMPLIANCE IS CHECKED FIRST AND ALWAYS. CODE QUALITY NEVER OVERRIDES A SPEC GAP.
```

## Process

1. **Confirm the work is locally green.** `verification-before-completion` first. Do not request review on red work.
2. **Collect the review inputs:**
   - `git diff` (or list of changed files)
   - Path to spec (`specs/<slug>.md`)
   - Path to plan (`.soup/plans/<slug>.md`)
3. **Dispatch `code-reviewer`** (via `Agent` tool). Expect a markdown with Findings structured per `schemas/qa_report.py::Finding`.
4. **Stage 1 response: spec compliance.** For each REQ flagged as missing or partial, plan a fix or surface to human. Do not proceed to Stage 2 issues if Stage 1 has gaps.
5. **Stage 2 response: code quality.** Prioritize critical/high findings. Group low severity into follow-up tickets if not blocking.
6. **Address or defer each finding explicitly.** "Addressed in commit abc" or "deferred to issue #123 because ...". No silent drops.
7. **Re-verify after fixes.** Then optionally re-review.

## Red Flags

| Thought | Reality |
|---|---|
| "Tests pass — skip review." | Reviewer catches what tests don't: unclear code, missing edge cases, spec drift. |
| "Reviewer said 'looks good'." | Ask for Findings list (can be empty). "LGTM" without enumeration is incomplete. |
| "Reviewer flagged a critical — let me argue it away." | Read `receiving-code-review`. Verify or implement; don't perform. |
| "I'll ignore style findings, fix criticals only." | Low findings accumulate. Triage them explicitly, don't drop silently. |
| "Review without a diff — reviewer can figure it out." | No. Provide the diff or the file list. |

## Related skills
- `verification-before-completion` — prerequisite
- `executing-plans` — review is part of QA gate
- `finishing-a-development-branch` — review decides merge path
