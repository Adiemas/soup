---
name: verification-before-completion
description: Use before claiming work is done, fixed, or passing — before committing or creating PRs. Requires running the verify_cmd fresh and quoting real output.
---

# Verification Before Completion

## Overview
You do not say "done", "fixed", "passing", "ready" without running the verification command fresh and quoting its real output. Confidence is not evidence.

## Iron Law
```
EVIDENCE BEFORE CLAIMS. ALWAYS. QUOTE THE verify_cmd OUTPUT OR DO NOT CLAIM COMPLETION.
```

## Process

1. **Identify the verify_cmd** for the task. From the plan, from the spec's acceptance, or from the standard stack check (`pytest`, `dotnet test`, `vitest run`, etc.).
2. **Run it fresh.** No cached results. No "it passed an hour ago". Fresh shell if environment state is suspect.
3. **Read the output.** All of it. Including warnings, deprecations, slow-test flags.
4. **Verify the claim.** Does the output *actually* prove what you're about to say? If you're claiming "all tests pass", does the summary say 0 failed?
5. **Quote the output** in your report. Last 30-50 lines is typical. Include the command.
6. **If output contradicts the claim, do not soften — retract.** Report the real state.

## Red Flags

| Thought | Reality |
|---|---|
| "Tests passed last run, it's fine." | Code changed since. Run fresh. |
| "Output is long — I'll summarize." | Summarize AFTER quoting. Raw evidence first. |
| "Warnings aren't errors, ignore them." | Some are. Read before dismissing. |
| "It built locally, ship it." | "Built" ≠ "tests pass". Separate commands. |
| "I'll claim done now and verify in CI." | CI is for catching regressions, not as your first test. Run locally first. |
| "Coverage dropped 2% — not a blocker." | Constitution IV.3: coverage <70% = NEEDS_ATTENTION. Real threshold, not feels. |

## Related skills
- `tdd` — the test being verified
- `executing-plans` — verify is the wave gate
- `requesting-code-review` — only after verify is green
- `finishing-a-development-branch` — verify blocks merge decisions
