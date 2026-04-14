# Incidents

This directory carries one file per production incident — novel
failures in running systems soup built, or in soup itself mid-run.
Each file is a completed postmortem.

## Incidents vs runbooks

Soup carries two operator artifact directories. They are easy to
conflate; they are not the same thing.

| Directory | Scope | Cadence | Template |
|---|---|---|---|
| `docs/runbooks/` | **Known** environmental failures. The fix is codified. Next engineer who hits the symptom gets the fix pasted in. | Edit the runbook when the fix changes. | `Symptom / Cause / Fix / Related` |
| `docs/incidents/` | **Novel** production failures. Postmortem + action items + link to retro. One file per event. | Append-only; never edit a past incident. | `docs/incidents/TEMPLATE.md` |

A third-time recurrence in `docs/incidents/` usually means the fix
should be extracted into `docs/runbooks/` — once a failure repeats,
the fix is no longer novel.

## Soup-native incident response flow

The `incident-responder` agent (see
`.claude/agents/incident-responder.md`) owns triage. The canonical
flow:

1. **Operator** receives an alert (Sentry, PagerDuty, Slack, a
   customer report). Severity estimate.
2. **Operator** invokes `incident-responder` via Claude Code with the
   symptom + time range.
3. **`incident-responder`** queries `soup logs search` +
   `soup logs tree`, traces the chain from log event to emitter to
   caller, cites the evidence by `session-<id>.jsonl#L<line>`.
4. **`incident-responder`** dispatches `test-engineer` to write the
   regression test (TDD iron law applies even in incident mode), then
   `verifier` to land the fix.
5. **`incident-responder`** drafts the postmortem at
   `docs/incidents/<YYYY-MM-DD>-<slug>.md` using `TEMPLATE.md`.
6. **Operator / team lead** reviews, fills the *Postmortem* section
   after the retro meeting, closes the incident.

## Filename convention

`docs/incidents/<YYYY-MM-DD>-<kebab-slug>.md`. Date is the UTC day
the incident started. The slug is short and specific
(`checkout-pool-exhaustion`, `rag-embedding-drift`, not `outage` or
`bug`).

## What every incident must carry

See `TEMPLATE.md` for the section layout. The non-negotiables:

- **Every log citation carries a line number.** Reviewers must be
  able to re-fetch the evidence from `logging/agent-runs/`. A
  paraphrased log entry is not valid evidence.
- **Every action item has an owner and a due date.** "Someone should
  fix this eventually" is not an action item.
- **Root cause is written with 5-whys.** Stop at "an engineer shipped
  a bug"; keep going until you hit a system-level cause (no test
  coverage, no alert on the regression, missing runbook).

## Relationship to the soup observability pillar

Incidents consume instrumentation. If a postmortem can't cite a log
line because the signal never existed, the *action items* include
adding it — via the relevant `rules/observability/*.md`. See
`docs/ARCHITECTURE.md §7` (observability pillar) for the full
instrumentation contract.

## Retention

Incidents are append-only and never deleted. A CAP / CLIA / SOX
audit will ask for the full history; keep it.
