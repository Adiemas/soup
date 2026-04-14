---
name: brainstorming
description: Use when starting any creative work — new feature, new component, new behavior, or modifying existing behavior — before writing a spec or plan. Explores intent and alternatives through Socratic dialogue.
---

# Brainstorming

## Overview
Before any creative work, explore intent and alternatives. Produce at least 2-3 framed options, not a single path. The goal is a validated problem definition and shortlisted approaches — not a solution.

## Iron Law
```
NO SPECIFICATION UNTIL 2-3 ALTERNATIVES HAVE BEEN NAMED, COMPARED, AND ONE PICKED WITH A WRITTEN REASON.
```

## Process

1. **Clarify the problem, not the solution.** Ask:
   - Who is this for? What outcome changes for them?
   - What is the current workaround? Why is it insufficient?
   - What's the success signal — a metric, a user action, a saved minute?
2. **Frame 2-3 alternatives.** For each, name it (A/B/C), one paragraph, and its key tradeoff. Include "do nothing" as option 0 if plausible.
3. **Compare on a small table.** Axes: user value, implementation cost, reversibility, blast radius, spec-complexity.
4. **Pick one + capture rationale.** A one-sentence "we pick A because ..." goes into the spec's Background section.
5. **Surface unknowns.** Enumerate open questions for `/clarify`. Do not pretend a hunch is a decision.
6. **Do NOT start writing code, tests, or a plan yet.** Output is text only.

## Red Flags

| Thought | Reality |
|---|---|
| "The answer is obvious, skip to plan." | Then writing it down takes two minutes. Do it. |
| "Only one real option exists." | Name the null hypothesis + one deliberately-bad straw man; the comparison still clarifies. |
| "We'll decide once we start coding." | You're conflating discovery with commitment. Discover first. |
| "The user asked for feature X, so just build X." | X is usually a proxy for an outcome. Surface the outcome. |
| "Let's pick the most flexible option." | "Flexible" often means unspecified. Pick the narrowest viable option. |

## Related skills
- `spec-driven-development` — what to do with the chosen alternative
- `writing-plans` — follows once the spec is approved
- `meta-prompting` — decomposing the plan into an ExecutionPlan
