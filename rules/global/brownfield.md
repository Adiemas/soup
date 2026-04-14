# Brownfield-First Protocol

_Applies to every modification of existing code. Greenfield scaffolding exempt (use templates)._

## Iron law

```
Read existing code + tests BEFORE proposing changes. Write regression tests BEFORE modifying observed behavior.
```

## Mandatory pre-edit checklist

Before proposing ANY edit to a file with existing production code:

1. **Read the file in full** (or the relevant class/module if >500 LOC — use `offset`/`limit`).
2. **Find the tests** for this code:
   - `git grep -l <symbol>` under `tests/`, `__tests__/`, or `*.Tests/`
   - If no tests exist → flag as high-risk; discuss with architect BEFORE editing.
3. **Run the existing tests** (via `verify_cmd` or `just test <path>`). Record the baseline: which pass, which fail, which are skipped.
4. **Read callers** — use `git grep -n <symbol>` or `researcher` agent to enumerate usage sites.
5. **Write a regression test** that captures the CURRENT observed behavior BEFORE you change it.
6. Only THEN make the change.
7. After the change, both: the new regression test and all prior tests must pass.

## When existing behavior is wrong

Three options (discuss + pick explicitly with user / architect):

1. **Preserve the bug, add the new feature on top.** Mark the bug with an `INCIDENT` ADR and a TODO referencing it. Lowest risk.
2. **Fix the bug as a separate commit/PR.** Regression-test the bug path too — the test should previously have failed because the behavior was wrong.
3. **Rewrite the module.** Requires architect approval + explicit ADR. Rarely the right answer.

## Rules for touching untested code

- Untested public function / endpoint → write at least one characterization test before editing. No exceptions.
- Untested critical path (auth, billing, migrations) → STOP. Escalate to architect. Do not edit on speculation.
- Untested utility (formatter, small helper) → characterization test still required but can be minimal.

## Anti-patterns

| Anti-pattern | Why it's wrong | Instead |
|---|---|---|
| "This code is obviously broken, let me just fix it." | You don't yet know the downstream contract | Characterize first. |
| "I'll refactor while I'm here." | Scope bloat; harder review | Separate PR, separate approval |
| "Tests are probably out of date, skip them." | They encode prior agreements | Read them; if outdated, update deliberately with rationale |
| "No tests exist, so behavior is undefined." | The behavior is whatever the callers observe | Enumerate callers; they ARE the tests |

## Hooks / enforcement

- `pre_tool_use.py` injects this rule set for `Edit` ops on existing files.
- `post_tool_use.py` logs whether tests ran before edit (heuristic: recent `verify_cmd` success in session).
- `verifier` agent flags PRs where an existing-file edit has no accompanying test change.

## When a test blocks you

A failing test may be a signal that:
- Your change broke a real contract → fix the change.
- The test encoded an outdated requirement → update the test WITH a spec change + rationale captured in the commit body.

Never delete or skip a test without explicit user / architect approval.
