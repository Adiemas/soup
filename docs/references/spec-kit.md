# spec-kit

GitHub's spec-driven development toolkit for agentic coding, built
around a deterministic pipeline of slash commands:
`/constitution → /specify → /clarify → /plan → /tasks → /implement →
/verify`. Each command consumes the prior artifact and produces the
next, so the human can review at any boundary without re-running the
whole chain. Relevance rating: 5/5 — the command surface is the
backbone of soup.

- URL: https://github.com/github/spec-kit
- Research summary: `research/08-sdd-testing.md`

## What we took

- The complete command pipeline verbatim, adapted to our stack.
- The distinction between **spec** (what + outcomes, frozen once
  approved) and **plan** (how + tech choices, may iterate).
- EARS phrasing for requirements ("The system shall...").
- `/clarify` as a mandatory ambiguity-resolution gate before `/plan`.
- Spec versioning: approved specs are frozen; changes spawn new
  versions, not diffs (Constitution I.4).
- Artifact directories: `specs/`, plans live alongside specs as
  `specs/<slug>-plan.md`.
