# Compliance rules

These rules are **flag-driven**, not stack-driven. The regular
`rules/<stack>/*.md` files are injected by `pre_tool_use.py` based on
file extension. Files in **this** directory are injected by
`subagent_start.py` based on the `compliance_flags[]` field of the
active intake form (`.soup/intake/active.yaml`, written by `/intake`).

Rules live here when they describe **what the app handles** (domain
data classes) rather than **what file you are editing** (stack).

## Flag → rule mapping

| `compliance_flag` | Rule file | Triggers on |
|---|---|---|
| `lab-data` | `rules/compliance/lab-data.md` | CAP/CLIA-adjacent lab workflows: calibration, QC, assay results, specimen tracking. |
| `pii` | `rules/compliance/pii.md` | Any app storing or transmitting identifiable employee / customer / patient personal data. |
| `phi` | `rules/compliance/phi.md` | HIPAA-adjacent: protected health information, or data that could reasonably be combined to identify a patient. |
| `financial` | `rules/compliance/financial.md` | SOX-adjacent: general-ledger adjacent, revenue recognition, audit-critical financial data. |

`public` and `internal-only` are **routing** flags, not compliance
flags — they do not trigger rule injection. They are enforced by
`security-scanner` severity policy instead.

## How injection works

1. `/intake` validates the YAML form and writes it to two locations:
   - `specs/<slug>-<YYYY-MM-DD>.intake.yaml` (audit trail, travels with the frozen spec).
   - `.soup/intake/active.yaml` (copy — always points at the most recent intake).
2. When a subagent starts, `subagent_start.py` reads
   `.soup/intake/active.yaml`, extracts `compliance_flags[]`, and
   appends the matching `rules/compliance/<flag>.md` files to the
   subagent's `additionalContext`.
3. `rules/global/*.md` is always injected (every subagent sees the
   baseline). Stack-specific rules still fire at Edit/Write time via
   `pre_tool_use.py`.

If `.soup/intake/active.yaml` is missing (e.g. the work started via
free-text `/specify` rather than `/intake`), injection is skipped
silently. Compliance rules can also be demanded explicitly in an agent
brief — but automatic injection is the norm.

## Multi-flag interaction

Flags stack. An app marked `pii` + `phi` receives BOTH rule files. The
validator in `schemas/intake_form.py` rejects mutually exclusive
combinations (`public` ⊥ `pii`/`phi`/`financial`/`internal-only`) at
intake time, so by the time these rules load the flag set is already
internally consistent.

## Not legal advice

These rule files encode Streck's operational expectations. They are
not substitutes for the compliance team's written policies and do not
constitute legal advice. When in doubt:

1. Escalate to the `requesting_team` named on the intake form.
2. Surface a `## Open questions` item and run `/clarify`.
3. Do not guess about retention windows, redaction scope, or BAA
   applicability.
