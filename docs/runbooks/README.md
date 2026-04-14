# Runbooks — known-failure recipes

Recipes for environmental and tooling failures that have bitten enough
real users that we've codified the fix. Each runbook is a short,
copy-paste-friendly artifact owned by the fixer, not the framework —
Soup links you here when a known symptom shows up so you don't rediscover
the trick from scratch.

## Purpose

1. **Save session-start tax.** If Claude hits a known error pattern
   (e.g. `module 'pkgutil' has no attribute 'ImpImporter'`), it should
   check the relevant runbook first instead of iterating on a fresh
   diagnosis.
2. **Preserve institutional memory.** When someone spends 40 minutes
   unwinding a docker-compose race, the fix lands here for the next
   engineer.
3. **Complement rules and skills.** `rules/` captures coding
   conventions; `.claude/skills/` captures process gates; `runbooks/`
   captures the specific workarounds for known-broken environments.

## Format convention

Every runbook follows this structure:

```markdown
# <title>

## Symptom
Concrete error text / observable behaviour.

## Cause
What's actually going on under the hood.

## Fix
Step-by-step recovery, preferring copy-pasteable commands.

## Related
Links to related rules / skills / agents.
```

Keep each runbook under ~2 KB. If the fix warrants more than a page,
that's usually a sign it should be a dedicated doc in `docs/` (or a
rule under `rules/`) with a link from here.

## How `session_start.py` surfaces runbooks

`.claude/hooks/session_start.py` scans this directory at session start
and appends a line to `additionalContext`:

> Runbooks available in `docs/runbooks/`: &lt;list&gt;. If Claude hits a known
> failure, check there first.

The hook caps the list at 6 titles to avoid context bloat — if you add
a seventh runbook, pick the least-urgent one to move into a linked
section instead of the top-level listing.

## Adding a new runbook

1. Create `docs/runbooks/<slug>.md` using the template above.
2. Keep the `## Symptom` section greppable — `session_start.py`
   (future work) may match user error text against symptom keywords.
3. Cross-reference related rules / skills / agents in `## Related`.
4. Do not mutate anything in `rules/` or `.claude/agents/` — runbooks
   are read-only artifacts for operators, not agent configuration.
