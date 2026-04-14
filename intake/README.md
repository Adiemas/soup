# Streck intake forms

Soup's preferred entry point for **new internal apps** is a structured
intake form, not a free-text `/specify` goal. The form is a YAML
document validated by
[`schemas/intake_form.py::IntakeForm`](../schemas/intake_form.py) and
consumed by the [`/intake`](../.claude/commands/intake.md) command.

> Already have a free-text idea and just want to sketch a spec?
> Use [`/specify "<goal>"`](../.claude/commands/specify.md). It is
> still supported. Prefer `/intake` whenever you are spinning up a
> brand-new app — the structured form removes a clarify round-trip
> and pre-populates the `## Integrations` section of the spec.

## Workflow

```
fill in YAML form  ──►  /intake --file <form.yaml>
                              │
                              ▼
                      schemas/intake_form.IntakeForm validates
                              │
                              ▼
                      spec-writer renders specs/<app_slug>-<date>.md
                              │
                              ▼
              /plan  (or /plan --architect-pre-pass for ≥3 integrations)
                              │
                              ▼
                      /tasks → /implement → /verify
```

Save your form under `intake/<your-app-slug>.yaml` (or anywhere — the
filename is not load-bearing). Two reference forms live in
`intake/examples/`:

- [`pipette-calibration-dashboard.yaml`](examples/pipette-calibration-dashboard.yaml)
  — multi-integration realistic example (REST + ADO + GitHub +
  Postgres + mail relay).
- [`asset-inventory-lite.yaml`](examples/asset-inventory-lite.yaml)
  — minimal example (GitHub + Postgres only).

## Field reference

All fields are required unless marked **optional**.

### Identity

| Field | Type | Notes |
|---|---|---|
| `app_slug` | kebab-case string | Drives `specs/<slug>-...`, `.soup/plans/<slug>...`, and the new-repo dir. Validator rejects underscores, uppercase, leading digits, and double hyphens. |
| `app_name` | string | Human-readable name displayed in UI/docs. |
| `description` | string (1-3 sentences) | Elevator pitch. |
| `intent` | string | The "why" — user value + business driver. Becomes the spec's `## Summary`/`## User outcomes` framing. |
| `requesting_team` | string | E.g. `"Lab Ops"`, `"Compliance"`. Owner of follow-ups. |
| `primary_users` | list[string] | Personas. Becomes `## Stakeholders & personas`. |

### Inputs / outputs

`inputs` and `outputs` use the same `IntakeField` shape so the
spec-writer can render them symmetrically into Functional Requirements.

| Subfield | Type | Notes |
|---|---|---|
| `name` | string | Snake-case identifier (e.g. `pipette_record`). |
| `description` | string | One sentence on what it carries. |
| `type` | enum | `text`, `number`, `file`, `image`, `api-call`, `other`. |

### Integrations (zero or more)

Each integration becomes a `## Integrations` bullet in the spec **and**
a `TaskStep.context_excerpts[]` hint downstream so specialist subagents
see the contract excerpt without re-discovering it.

| Subfield | Type | Notes |
|---|---|---|
| `kind` | enum | `github-repo`, `ado-project`, `rest-api`, `graphql-api`, `database`, `sftp`, `s3`, `other`. |
| `ref` | string | Locator: URL, `org/repo`, ADO project name. |
| `purpose` | string | What this app reads or writes against the integration. |
| `auth` | enum | `pat`, `oauth`, `api-key`, `none`, `tbd`. |

### Stack & deployment

| Field | Type | Notes |
|---|---|---|
| `stack_preference` | enum | One of the canonical [`/soup-init`](../.claude/commands/soup-init.md) templates: `python-fastapi-postgres`, `dotnet-webapi-postgres`, `react-ts-vite`, `fullstack-python-react`, `nextjs-app-router`, `ts-node-script`, or `no-preference`. |
| `deployment_target` | enum | `internal-docker`, `azure`, `vercel`, `on-prem`, `tbd`. |

### Outcomes & constraints

| Field | Type | Notes |
|---|---|---|
| `success_outcomes` | list[string] | Testable. E.g. "P95 export <= 5s". Becomes `## Acceptance criteria`. |
| `constraints` | list[string] (optional) | Regulatory / performance / budget caps. Becomes `## Non-functional requirements`. |
| `deadline` | ISO date or null (optional) | `YYYY-MM-DD`. Quoted in YAML so it stays a string. |
| `compliance_flags` | list[enum] (optional) | `pii`, `phi`, `financial`, `lab-data`, `public`, `internal-only`. Drives rule injection. `public` is mutually exclusive with `internal-only`/`pii`/`phi`/`financial`. |

## Tips

- **Keep it short.** The intake form is not the spec. Aim for one
  page on screen. Detail belongs in the spec the `spec-writer` will
  produce.
- **Be honest about integrations.** Listing five integrations triggers
  the architect pre-pass under `/plan`; under-listing them buys you a
  round of `/clarify` instead.
- **Use `tbd` instead of guessing.** `auth: tbd` is a legitimate
  intake answer; `auth: pat` because "we usually do PAT" is not.
- **Compliance flags drive policy.** `pii`/`phi`/`financial` raise the
  `security-scanner` severity floor and force an audit-log requirement
  in the spec. `lab-data` adds the 7-year retention reminder.
- **Validate before committing.** Run
  `python -c "from schemas.intake_form import IntakeForm;
  IntakeForm.from_yaml('intake/<your-app>.yaml')"` to catch errors
  before invoking `/intake`.

## Why YAML and not a Pydantic JSON?

Engineers fill these in by hand. YAML's block scalars (`>` and `|`)
keep the multi-paragraph `description`, `intent`, and outcome strings
diff-friendly and reviewable in a PR. The schema is the same either
way — `IntakeForm.model_validate({...})` works on a JSON dict too if
you would rather generate the form programmatically.
