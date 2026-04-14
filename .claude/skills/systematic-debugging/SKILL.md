---
name: systematic-debugging
description: Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes. Enforces a 4-phase root-cause loop and 3-strike escalation.
---

# Systematic Debugging

## Overview
Bugs are investigated in four phases before any code change: **Investigate → Pattern analysis → Hypothesis → Implementation**. Three failed fixes on the same defect escalate to the architect. Guessing is blocked.

## Iron Law
```
NO FIX BEFORE A WRITTEN HYPOTHESIS BACKED BY EVIDENCE. 3 FAILED FIXES → ESCALATE.
```

## Process

### Phase 1 — Investigate
1. Reproduce the failure deterministically. Record exact command, env, commit SHA.
2. Collect the full failure signature: stderr, stack, test name, inputs, outputs.
3. Identify the smallest failing input.

### Phase 2 — Pattern analysis
4. Read the failure. What class of bug is this? (null/boundary/async/concurrency/env/data)
5. Search the repo for similar patterns — have we seen this shape before?
6. Read the *changed* code since last green. Binary-search commits if needed.

### Phase 3 — Hypothesis
7. Write ONE hypothesis: "The failure occurs because X, supported by evidence Y."
8. Predict what a minimal fix would change. If the fix changes 6 things, you don't have a hypothesis; you have a wish.
9. Design a minimal test that distinguishes hypothesis from null. Run it.

### Phase 4 — Implementation
10. Apply the minimal fix. Run the failing test + the full suite.
11. On green: commit with the hypothesis in the commit body.
12. On red: new hypothesis, new test. Do NOT iterate edits blindly.

### Escalation
- After 3 failed attempts on the same defect, STOP. Dispatch to `architect` with: all hypotheses tried, evidence collected, what changed each time.

## Red Flags

| Thought | Reality |
|---|---|
| "Let me try adding a null check here." | Why there? Evidence? If you can't cite evidence, it's a guess. |
| "Retry and hope it's flaky." | Flake is a finding. Record it; don't paper over. |
| "Print-debugging will find it faster." | Maybe, but commit the discovery as a test — don't delete the prints and forget. |
| "Fix attempt 4 might work." | Constitution IX.1: escalate after 3. Architect sees patterns you don't. |
| "The bug is obviously in library X." | Evidence that you've ruled out your own code? If not, not obvious. |

## Related skills
- `tdd` — the test that drives the fix
- `verification-before-completion` — proving the fix holds
- `requesting-code-review` — second set of eyes before shipping the fix
