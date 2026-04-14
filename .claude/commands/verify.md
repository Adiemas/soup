---
description: Run QA gate on current branch. Dispatches code-reviewer + security-scanner + verifier in parallel; synthesizes QAReport.
argument-hint: []
---

# /verify

## Purpose
Run the QA gate as a standalone command (also auto-triggered by Stop hook). Produces a `QAReport` with verdict `APPROVE | NEEDS_ATTENTION | BLOCK` per `schemas/qa_report.py`.

## Workflow
1. Invoke `qa-orchestrator` (sonnet) with:
   - Current diff vs `main` (or `git merge-base`).
   - Paths touched.
   - Plan reference (if a run is active).
2. `qa-orchestrator` dispatches in parallel via Agent tool:
   - `code-reviewer` — spec compliance + style + readability.
   - `security-scanner` — OWASP + secrets + supply chain.
   - `verifier` — runs all declared `verify_cmd`s from the active plan; also runs `just test` if present.
3. Synthesize findings into `QAReport`. Apply blocking rules:
   - Any critical security → BLOCK.
   - Any failing test → BLOCK.
   - ≥3 critical correctness → BLOCK.
   - Coverage < 70% → NEEDS_ATTENTION.
4. Emit report to `.soup/runs/<run_id>/qa_report.json` + markdown summary.

## Output
- Verdict.
- Findings table (severity / category / file:line / message).
- Test summary (passed/failed/skipped/coverage).
- Actionable next steps per finding.

## Notes
- Report is immutable; re-running `/verify` creates a new report with new id.
- On BLOCK, do NOT proceed to PR. Fix and re-verify.
