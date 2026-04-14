---
description: Cross-agent peer review on current diff. Cycle 1 runs code-reviewer + security-scanner in parallel; optional `--rounds N` adds red-team + over-eng critics on round ≥2.
argument-hint: [base-ref] [--rounds N]
---

# /review

## Purpose
Request independent peer review of the current diff without running full `/verify`. Useful before opening a PR.

Supports a **multi-round** mode that adds adversarial (`red-team-critic`) and
radical-simplification (`over-eng-critic`) reviewers on round ≥2. This addresses
the cycle-1 dogfood finding (`docs/real-world-dogfood/claude-news-aggregator.md`
§"red-team / radical-simplification critic pass") that a single-pass review
missed classes of issues the target repo's own multi-round plan cadence caught.

## Variables
- `$ARGUMENTS` — optional base ref (default `main` or `origin/main`) and
  optional `--rounds N` flag.
- **`--rounds N`** — integer, default `1`. Round 1 is the cycle-1 pass
  (`code-reviewer` + `security-scanner`). Rounds ≥ 2 additionally dispatch
  `red-team-critic` + `over-eng-critic` in parallel. Typical values:
  - `1` — quick pre-PR pass (default).
  - `2` — plan or diff under pressure; adversarial + simplification lens.
  - `3+` — rare; use when the diff is large and the stakes are high.

## Workflow
1. Compute diff: `git diff <base-ref>...HEAD`.
2. **Round 1 (always)** — dispatch in parallel via `Agent` tool:
   - `code-reviewer` — spec compliance, clarity, idioms per stack rules.
   - `security-scanner` — secrets, OWASP, supply chain. Respects
     repo-level `.gitleaks.toml` if present.
3. **Round ≥ 2 (if `--rounds N` with N ≥ 2)** — in parallel with round-1
   findings passed as "prior findings" context to avoid duplication:
   - `red-team-critic` — asks "how does this fail?" Emits a structured
     `CritiqueReport` to `.soup/reviews/<ts>-red-team.json`.
   - `over-eng-critic` — asks "what's unnecessary?" Emits a
     `CritiqueReport` to `.soup/reviews/<ts>-over-eng.json`.
   Both critics are read-only (Read/Grep only) and orthogonal to
   cycle-1 reviewers — they don't duplicate lint-and-spec-compliance
   checks.
4. Synthesize all reviews into `.soup/reviews/<ts>.md`:
   - `## Code review` — findings + praise + suggestions.
   - `## Security` — findings + severity.
   - `## Red team` *(if round ≥ 2)* — concerns + attack vectors + severities.
   - `## Over-engineering` *(if round ≥ 2)* — deletion targets + rationale.
   - `## Consolidated action items` — numbered, deduped across rounds,
     sorted by severity.

## Output
- Path to review markdown (`.soup/reviews/<ts>.md`).
- Per-round paths to `CritiqueReport` JSON files (if round ≥ 2).
- Counts per severity (aggregated).
- Blocking issues (if any).

## Notes
- `/review` does NOT run tests; use `/verify` for full gate.
- Findings are advisory here; `/verify` is authoritative for gating.
- Round ≥ 2 adds wall-clock time roughly equal to round 1 (critics run in
  parallel with each other). Budget accordingly.
- Critics are paired by design — `red-team` without `over-eng` tends to
  pile on concerns; `over-eng` without `red-team` tends to under-weight
  resilience. Together they produce a balanced critique.
