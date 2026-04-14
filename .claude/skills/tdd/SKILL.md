---
name: tdd
description: Use when implementing any feature or bugfix, before writing implementation code. Enforces RED/GREEN/REFACTOR with auto-deletion of pre-test code.
---

# Test-Driven Development

## Overview
Every behavior is driven by a test that fails first. Code written ahead of a failing test is deleted. The cycle is RED (failing test) → GREEN (minimum code) → REFACTOR (only if still green).

## Iron Law
```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST. PRE-TEST CODE IS DELETED.
```

## Process

1. **Read the acceptance criteria.** What observable behavior must exist after this task?
2. **Write the failing test (RED).**
   - One test per behavior (or one parametrization group).
   - Assert on the behavior, not implementation details.
   - Use existing fixtures; don't re-invent.
3. **Run the test. Confirm it fails for the right reason.**
   - "Import error" or "name not defined" = wrong mode. Rewrite the test so it fails on a *missing assertion*, not a typo.
   - Quote the failing output.
4. **Write the minimum code to turn GREEN.**
   - Smallest diff possible. Do not gold-plate.
   - Stay inside `files_allowed`.
5. **Re-run the test. Confirm GREEN.** Quote output.
6. **REFACTOR.** Only clarity/structure improvements that keep all tests green. Re-run after each.
7. **Commit atomically.** One task, one commit.

## Red Flags

| Thought | Reality |
|---|---|
| "I already wrote the impl, let me add a test to cover it." | Delete the impl. Write the test first. No shortcuts. |
| "The test is trivial — skip it." | Trivial tests catch trivial regressions, which are the most common kind. |
| "Test passes on first run." | Then it wasn't driving the design. Rewrite so it fails first. |
| "It's hard to test — I'll ship it untested." | Hard-to-test == bad design. Refactor the design. |
| "The failing reason is an import error, close enough." | Not close enough. Fix the test so the failure is *behavioral*. |
| "Refactor while red, why not?" | Refactoring on red hides bugs. Green first. |

## Related skills
- `writing-plans` — every task in the plan is TDD-shaped
- `subagent-driven-development` — test-engineer + implementer pair
- `verification-before-completion` — the gate after GREEN
- `systematic-debugging` — when the test fails for an unexpected reason
