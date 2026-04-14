# Iteration 3 dogfood — greenfield → deploy walkthrough

**Date:** 2026-04-14
**Mode:** Simulated greenfield-from-intake, carried past `/verify` into deploy.
**Subject:** Where does soup stop? The intake → implement → verify loop is
well-paved; deploy is a cliff. This report traces the cliff and proposes the
minimum viable additions to close the loop.

Walked
[`intake/examples/asset-inventory-lite.yaml`](../../intake/examples/asset-inventory-lite.yaml)
(slug `asset-inventory-lite`, `stack_preference: fullstack-python-react`,
`deployment_target: internal-docker`, one GitHub integration, one Postgres
integration, `internal-only` compliance). Picked the simpler example — iter-2
already exercised the 5-integration pipette dashboard.

## Walkthrough

### Step 1 — `/soup-init fullstack-python-react asset-inventory-lite`

Note: the intake `stack_preference` is `fullstack-python-react`. `soup-init`
resolves `templates/fullstack-python-react/` (which has both a `backend/` and
`frontend/` tree) into `../asset-inventory-lite/`, substitutes
`{{APP_NAME}}`, runs `git init`, copies `.env.example → .env`, writes a
project `CLAUDE.md` that defers to this soup repo, runs `just init`.

Outcome: a working repo with `docker-compose.yml`, `Dockerfile` (backend
only — the React frontend is built into `backend/app/static/` or served
separately; the template is ambiguous and worth checking before real use).
No `.github/workflows/`, no `azure-pipelines.yml`, no `vercel.json`, no
runbook templates. Deploy scaffolding is **entirely absent** from the
template tree (verified: `ls templates/python-fastapi-postgres/.github` →
no such dir).

### Step 2 — `/intake --file intake/examples/asset-inventory-lite.yaml`

- `IntakeForm.from_yaml` parses cleanly (validates against
  `schemas/intake_form.py`).
- `integrations[0].kind == "github-repo"`,
  `ref == "streck/lab-design-system"`. The command's auto-prompt heuristic
  ([`intake.md:52-59`](../../.claude/commands/intake.md)) asks:
  "looks like an existing repo. Re-run with `--brownfield`?" The operator
  says no (it's a dependency, not a parent codebase).
- Emits `specs/asset-inventory-lite-2026-04-14.md` and stashes
  `specs/asset-inventory-lite-2026-04-14.intake.yaml`, mirrored to
  `.soup/intake/active.yaml`.
- `## Integrations` section has two anchored subsections:
  `#integration-github-repo-streck-lab-design-system` and
  `#integration-database-postgres-lab-ops-db-streck-internal-lab-ops`.
- Routes: `/plan` (only 2 integrations, no architect pre-pass trigger).

### Step 3 — `/plan`

- Reads `.soup/intake/active.yaml`. Extracts `stack_preference`,
  `deployment_target: internal-docker`, `compliance_flags: [internal-only]`,
  integrations.
- `architect` (opus) produces architecture doc. Honours
  `fullstack-python-react` stack without re-deriving. Notes
  `internal-only` implies VPN-only ingress + no public DNS.
- `plan-writer` (sonnet) emits `.soup/plans/asset-inventory-lite.md` with
  `## Architecture`, `## File map`, `## Task outline`, `## Budget`.

**First deploy gap surfaces here.** `/plan`'s required sections
([`plan.md:49`](../../.claude/commands/plan.md)) do not include a `## Deploy`
or `## Release` section. `deployment_target: internal-docker` is consumed by
the architect only as a narrative constraint — no concrete "produce
a Dockerfile for prod, publish to the Streck registry, PR a compose
override into the internal-docker-host repo" task ever lands in
`## Task outline`. The intake YAML's deployment metadata dies at
`/plan`.

### Step 4 — `/tasks`

- `tasks-writer` converts the markdown plan to
  `.soup/plans/asset-inventory-lite.json`.
- For each impl task T: emits `test-T` + `impl-T` step pair.
- `context_excerpts` on each integration-adjacent step points at the
  per-integration anchor (e.g. the Postgres adapter impl step cites
  `specs/asset-inventory-lite-2026-04-14.md#integration-database-postgres-lab-ops-db-streck-internal-lab-ops`).
- Validates via `soup plan-validate`. All agents in `library.yaml`.

**Second deploy gap.** No `deploy-*` step shapes. The ExecutionPlan ends at
the last `impl-*` step. There is no canonical "final wave writes the
Dockerfile" or "final wave drops a GHA workflow" step, because there is
no agent to assign such a step to and no `rules/deploy/` for it to consult.

### Step 5 — `/implement` (simulated)

Waves 1-N execute. Wave 1 is typically scaffolding (Pydantic models, DB
wrapper). Wave 2-3 are endpoints + frontend components. Wave N is usually
integration wiring. Each wave: orchestrator spawns fresh subagents, each
runs in a worktree, verifies, commits. QA gate at end.

The template's `just up` (`docker compose up -d --build`) works locally.
No agent has written a `Dockerfile.prod` or multi-arch build config; the
template's `Dockerfile` is dev-oriented (no healthcheck, no non-root user
for the backend — the Next.js template gets this right, the FastAPI one
doesn't).

### Step 6 — `/verify`

QA gate runs. `code-reviewer` + `security-scanner` + `verifier` in
parallel. Findings synthesised into `QAReport`. On APPROVE,
`/verify` suggests `gh pr create`.

This is the last step soup has opinions on.

### Step 7 — Deploy (the cliff)

The engineer now owns:

1. **Build the image.** Template has a working `Dockerfile`. No `.github/workflows/docker-publish.yml`. No image-registry convention documented. No SBOM generation. No image signing. No vulnerability scan wiring (trivy/grype). The `security-scanner` agent scans *code*, not *images*.
2. **`docker-compose up` locally.** Template works. Postgres healthcheck present. Backend has no healthcheck.
3. **Deploy per `deployment_target`.**
   - `internal-docker`: engineer must know the Streck internal docker host, the compose-override convention, the VPN ingress config, the audit-log shipping target. None of this is in the repo. None of this is in `docs/runbooks/`.
   - `azure`: no App Service deploy template, no `az webapp` wrapper in `cli_wrappers/`, no ARM/Bicep, no `azure-pipelines.yml`.
   - `vercel`: template has no `vercel.json`. Framework has Vercel plugin skills available (`vercel:deploy`, `vercel:deployments-cicd`, `vercel:env-vars`, `vercel:marketplace`) but **no soup-owned rule or agent invokes them**. The Vercel skills exist at the Claude Code harness level, not in `rules/` or `.claude/agents/`.
   - `on-prem`: no story at all.
4. **CI/CD.** No `.github/workflows/ci.yml` exists in any template. No ADO pipelines. Framework-level CI (`.github/workflows/ci.yml` on soup itself) exists for soup's self-tests, but it's not copied into scaffolded apps.
5. **Smoke tests.** No convention for "after deploy, hit `/health` and assert 200." The Next.js template has an e2e `health.spec.ts` (playwright); the FastAPI template has `tests/test_health.py` (unit, not remote).
6. **Rollback.** No runbook. No "previous image tag is always retained." No DB rollback story beyond `migrate-down` (which is a single-version-back, not a tagged rollback).
7. **Observability.** `rules/global/logging.md` exists (soup repo level) but does not prescribe shipping logs off-box. No Sentry/Datadog/App Insights wiring. No metrics convention. No tracing.

## Current state: what soup handles vs what stops at `/verify`

| Concern | Soup covers? | Evidence |
|---|---|---|
| Spec | YES | `/intake`, `/specify` + `spec-writer` |
| Architecture + tech choices | YES | `/plan` + `architect` (honours intake `stack_preference`) |
| TDD task decomposition | YES | `/tasks` + `tasks-writer`, schema-validated |
| Wave execution | YES | `/implement` + `orchestrator` + worktrees |
| Code review | YES | `code-reviewer` |
| Security scan (code-level) | YES | `security-scanner` + compliance-flag-driven severity floor |
| Test execution | YES | `verifier` + Stop-hook QA gate |
| Regression baseline | PARTIAL | `regression_baseline_cmd` exists but only runs pre/post **wave execution**, not pre/post **deploy** |
| **Docker image build for prod** | NO | Template has a dev `Dockerfile`; no prod variant, no tag strategy |
| **Image registry publish** | NO | No workflow, no `cli_wrappers/docker_publish.py` |
| **CI/CD wiring (GHA or ADO)** | NO | No workflows shipped with templates |
| **Cloud-specific deploy** | NO | `DeploymentTarget` enum has 4 values; 0 rules files |
| **Vercel plugin skill integration** | NO | Skills exist at harness level; no soup-side glue |
| **Post-deploy smoke tests** | NO | No "deploy then curl /health" step shape |
| **Rollback runbooks** | NO | `docs/runbooks/` has 5 incident files, 0 deploy rollbacks |
| **Observability wiring** | NO | `rules/global/logging.md` is dev-local only |
| **Secrets → prod** | NO | `.env.example` is the contract for local dev; no vault/CI-env story |

## Gaps — ranked

### CRITICAL

- **C1. No `deployer` agent + no `deploy.md` command.** The canonical flow
  (`/constitution → /specify → /clarify → /plan → /tasks → /implement →
  /verify`) terminates with "next step: `gh pr create`". Nothing after
  that is soup's problem — but `deployment_target` is a mandatory intake
  field with 4 cloud/platform options, and soup captures it only to drop
  it. The framework *asks* where this ships and then shrugs.
- **C2. Templates are not deploy-ready.** No prod `Dockerfile` (multi-stage
  yes, but no non-root user for the FastAPI template, no healthcheck, no
  labelled OCI annotations). No `.github/workflows/`. No `azure-pipelines.yml`.
  No `vercel.json`. The first thing the engineer does after `/verify` is
  write all of this from scratch, every time, without soup steering.
- **C3. No rules for any deploy target.** `DeploymentTarget` is
  `internal-docker | azure | vercel | on-prem | tbd`. `rules/` has 9
  folders — 0 of them are `deploy/`. Specialist subagents writing deploy
  code have zero rules injected for this domain.

### HIGH

- **H1. `regression_baseline_cmd` only covers wave execution, not deploy.**
  The iter-2 improvement (baseline capture pre/post waves in
  [`implement.md:18-23`](../../.claude/commands/implement.md)) is a
  beautiful pattern — and it stops before deploy. No `pre_deploy_cmd` /
  `post_deploy_cmd` analogue that would let the orchestrator assert
  "the `/health` endpoint returned the same schema before and after the
  deploy."
- **H2. Vercel plugin skills are invisible to soup.** The harness offers
  `vercel:deploy`, `vercel:deployments-cicd`, `vercel:env-vars`,
  `vercel:marketplace` — rich, current, production-quality. Soup has no
  way to invoke them. A `deployer` agent card could whitelist these and
  wire them into a Vercel-deploy wave.
- **H3. Secrets pipeline is undocumented.** Constitution Article VI says
  "no secrets in code"; `.env.example` is the local contract. But moving
  from `.env` to "deployed app has `POSTGRES_PASSWORD` set" is left to
  the reader. No rules/docs on Azure Key Vault, ADO Library, GHA
  Secrets, Vercel Env, or Streck's internal vault.
- **H4. No deploy-preview-URL convention.** Modern Streck workflow
  assumes "every PR gets a preview URL" (Vercel does this natively;
  Azure needs slot-swap; internal-docker needs per-branch compose
  project names). Soup has no opinion, so preview URLs are not in the
  PR description template and not checked by `code-reviewer`.

### MEDIUM

- **M1. No smoke-test shape in `ExecutionPlan`.** A deploy wave needs
  "after the image is live, curl `/health`, assert 200, assert
  schema matches `specs/<slug>.md#health-contract`". Today this would
  have to be shoehorned into `verify_cmd`, which runs against a
  worktree, not a remote host.
- **M2. No rollback runbook.** `docs/runbooks/` has `anthropic-rate-limit.md`,
  `postgres-container-not-ready.md`, etc. — all good. None cover "deploy
  broke prod, here's how to roll back."
- **M3. Observability wiring is orthogonal to `deployment_target`.**
  Internal-docker probably ships logs to the Streck Splunk; Azure App
  Service likely wires to App Insights; Vercel to its own log drain.
  These are all valid; soup has no target-conditional injection.
- **M4. Compliance flags don't touch deploy.** `internal-only` should
  raise red flags if the chosen deploy target is `vercel` (public CDN).
  No validator catches that today. `IntakeForm._flags_are_consistent`
  checks `public` vs `internal-only` but not `internal-only` vs
  `deployment_target: vercel`.

## Proposed additions

Concrete, bounded, each shippable as its own PR. Ordered by leverage.

1. **`.claude/commands/deploy.md`.** New command, flow:
   1. Read `.soup/intake/active.yaml`; resolve `deployment_target`.
   2. Dispatch `deployer` agent (new, see #2) with target + app slug +
      current git SHA.
   3. Agent produces a `DeployPlan` (new schema — see #7) with steps:
      `image-build → image-publish → env-sync → deploy → smoke-test →
      health-assert`. Each step has `verify_cmd`.
   4. Optional `--dry-run` flag prints the plan without executing.
   5. Runs `plan.regression_baseline_cmd` against the **remote** host
      pre- and post-deploy when provided.

2. **`.claude/agents/deployer.md`.** New specialist (sonnet tier).
   - `files_allowed`: `Dockerfile*`, `.github/workflows/**`, `azure-pipelines.yml`, `vercel.json`, `docker-compose*.yml`, `deploy/**`.
   - Reads `rules/deploy/<target>.md` + `rules/deploy/secrets.md`.
   - Whitelisted skills (Vercel targets): `vercel:deploy`,
     `vercel:deployments-cicd`, `vercel:env-vars`,
     `vercel:marketplace`.
   - Invoked only by `deploy.md` — never by `/implement` (Article III —
     implementers write code, not infra).

3. **`rules/deploy/internal-docker.md`.** Conventions for Streck's
   internal docker host: image tag format (`<slug>:<sha>-<branch>`),
   compose-override shape, VPN ingress, log shipping target, audit
   requirements when `lab-data` or `internal-only` set.

4. **`rules/deploy/azure-app-service.md`.** `az webapp deployment
   source config-zip` vs container-deploy; slot-swap for blue-green;
   App Insights connection-string env var convention; Managed Identity
   over connection strings.

5. **`rules/deploy/vercel.md`.** When to use `vercel:deploy` vs
   `vercel:deployments-cicd` (one-off vs wired-into-CI); `vercel env pull`
   into local `.env.local`; preview-URL PR comment convention;
   `internal-only` compliance flag + Vercel = hard error (warn at
   `/intake` too — see proposal #8).

6. **`rules/deploy/{github-actions,ado-pipelines}.md`.** Two flavours,
   same skeleton: checkout, cache, build, test, image-build+publish,
   deploy (gated by environment), smoke-test, rollback-on-failure.
   Reference the per-target deploy rule for the "deploy" step body.

7. **`schemas/deploy_plan.py` + `cli_wrappers/docker_publish.py` +
   `cli_wrappers/gh_deploy.py`.** `DeployPlan` validates the step
   list (types: `build | publish | env-sync | migrate | deploy |
   smoke | post-verify | rollback`). CLI wrappers give `deployer`
   reliable, haiku-callable commands (iter-2 pattern: haiku drives,
   wrapper enforces flags — same reason `cli_wrappers/psql.py` exists).

8. **Intake validator: `deployment_target` vs `compliance_flags`.**
   Extend `IntakeForm._flags_are_consistent`: `internal-only` +
   `deployment_target: vercel` → `ValueError`. Add `public` + `on-prem`
   → warn (not error — there's a legit case). Adds ~10 LOC to
   `schemas/intake_form.py`, catches the most expensive intake mistake
   possible.

9. **Runbooks: `docs/runbooks/deploy-rollback-{docker,azure,vercel}.md`.**
   Three short incident-response docs. Same shape as the existing
   `npgsql-utc-datetime.md` — symptom, diagnosis, fix, prevention.

10. **Template deploy scaffolding.** Add to every template under
    `templates/<template>/`:
    - `.github/workflows/ci.yml` (lint + test; matches the repo's CI).
    - `.github/workflows/deploy.yml` stub with `if: github.event.inputs.target`
      dispatching per `deployment_target`.
    - A `deploy/` dir with a `README.md` linking to the right
      `rules/deploy/<target>.md`.
    - For `python-fastapi-postgres`: `Dockerfile.prod` with non-root
      user + healthcheck (fix the gap the Next.js template already
      handles correctly).

## What pairs well with the iter-2 improvements

- **Baseline capture around deploy.** Iter-2 wired
  `regression_baseline_cmd` pre/post wave execution. The same primitive
  extends cleanly: add `deploy_baseline_cmd` (optional) on the
  `DeployPlan`; run it against the remote host pre- and post-deploy.
  Any regression in the endpoint-response diff becomes a QA finding.
  Zero new primitives — one new field, same machinery. See proposal #1.
- **Per-integration anchors survive into deploy.** Iter-2's
  `#integration-<kind>-<ref-slug>` anchor system was motivated by
  "specialist subagents should load only one integration's slice." The
  `deployer` agent benefits identically: when writing the Postgres
  sidecar section of the compose override, it loads
  `#integration-database-...`, not the whole spec.
- **Compliance-flag severity uplift extends to image scanning.** The
  `security-scanner` already consults `compliance_flags` to raise
  severity on PII/PHI/financial findings. Same pattern applies to the
  image scan in the deploy wave: `internal-only` with a high-severity
  image CVE is a `BLOCK`; `public` without a CVE budget documented is
  also a `BLOCK`. Reuse the existing severity-floor primitive from
  `rules/compliance/README.md`.
- **Intake YAML as audit trail through to deploy.** The stashed
  `specs/<slug>-<date>.intake.yaml` is immutable (Article I.4). It already
  travels with the spec into `/plan`. It should also travel into
  `/deploy` — the deployer reads `deployment_target` from the same
  stash, and the deploy run is recorded under `.soup/runs/<run_id>/deploy.json`
  with a pointer back to the intake YAML SHA, closing the audit loop
  from intake → production.

## Summary

Soup is a 6-of-7 framework today: intake through verify is paved; deploy
is bare earth. The fix is a modest addition — one command, one agent,
five rules files, three runbooks, a schema, two CLI wrappers — that
respects every existing pattern (agent tiering, rule injection, schema
validation, compliance-flag uplift, baseline capture). The Vercel plugin
skills are a free accelerator for `deployment_target: vercel` the moment
a `deployer` agent exists to invoke them. Intake asks `deployment_target`
for a reason — soup should answer.
