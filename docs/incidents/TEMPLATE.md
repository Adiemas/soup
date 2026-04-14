# <YYYY-MM-DD> — <one-line title>

<!--
Filename: docs/incidents/<YYYY-MM-DD>-<slug>.md
Keep each incident under ~6 KB. If you need more, split the retro
into a linked doc rather than bloating this file.
-->

## Summary

One paragraph: what happened, to whom, for how long. Plain language;
no jargon. A stakeholder who does not work on this system should be
able to understand this section in under 30 seconds.

## Impact

- **Affected users:** <N users / tenants / requests>
- **Affected surface:** <endpoints / jobs / UI surfaces>
- **Duration:** <start_ts UTC> to <end_ts UTC> (<HH:MM> total)
- **Error rate:** <peak error rate, e.g. "12% of `/api/checkout`
  requests over 8 minutes">
- **Revenue / regulatory impact:** <if any; link to financial or
  compliance notification>
- **Severity:** SEV1 | SEV2 | SEV3 | SEV4

## Timeline

All timestamps UTC. Lift from the structured logs where possible;
cite by `session-<id>.jsonl#L<line>`.

| Time (UTC) | Event |
|---|---|
| HH:MM | Alert fires: `<alert name>` |
| HH:MM | On-call paged |
| HH:MM | Hypothesis formed: <one line> |
| HH:MM | Mitigation applied: <one line> |
| HH:MM | Error rate returns to baseline |
| HH:MM | All-clear |

## Root cause

5-whys. Keep going until you hit a system-level cause, not an
individual mistake.

1. **Why did the surface fail?** <observable>
2. **Why did that happen?** <proximate mechanism>
3. **Why was it possible?** <class of error>
4. **Why was it not caught?** <missing test / alert / runbook>
5. **Why is the system designed such that this was not caught?**
   <architectural / organizational cause>

Quote the load-bearing log line(s) inline:

```
<session-abc123.jsonl#L47>  {"ts": "...", "event": "Checkout.Charge_failed", ...}
```

## Contributing factors

Everything that made this incident worse or more likely that is not
the root cause:

- <e.g. "no runbook existed for pool exhaustion">
- <e.g. "dashboard's p99 chart hides sub-minute spikes">
- <e.g. "on-call paging routed to a stale rotation">

## What went well

List the mitigations that worked. This section is not optional — it
reinforces what to keep doing and prevents well-meaning rewrites of
things that are already correct.

- <e.g. "correlation ids let us isolate the 3 affected tenants in <5 min">
- <e.g. "feature flag rollback took 90 seconds">

## Action items

Every item has an owner + a due date. "Team" is not an owner.

| Owner | Due | Task | Tracking |
|---|---|---|---|
| @alice | 2026-04-21 | Add pool-saturation alert at 80% | JIRA-1234 |
| @bob | 2026-04-28 | Add regression test for `charge()` pool release | PR link |
| @team-lead | 2026-04-16 | Update `rules/observability/metrics.md` to require pool-saturation metric | PR link |

## References

- Alert: <link to alert in Sentry / PagerDuty>
- Dashboard: <link>
- Related incident(s): <link to prior similar>
- Fix PR: <link>
- Runbook (if extracted): <link>
- Retro meeting notes: <link>

## Postmortem

*(Filled after the retro meeting.)*

Lessons + the honest "what would we do differently." Short. No
blame. System-level.
