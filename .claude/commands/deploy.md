---
description: Deploy the current app per IntakeForm.deployment_target. Invokes the deployer agent only after /verify returns APPROVE.
argument-hint: "[--target <internal-docker|azure|vercel|on-prem>]"
---

# /deploy

## Purpose
Close the intake → implement → verify → **deploy** loop. Dispatches the
`deployer` agent (sonnet) to ship the current plan's output to the
`deployment_target` declared on the stashed intake form. The deployer
runs a post-deploy smoke test and the optional
`deploy_baseline_cmd`, then emits a `DeployReport` JSON with verdict
`deployed | refused | rolled-back | regression`.

## Variables
- `$ARGUMENTS` — optional flags. Today only `--target <override>` is
  recognised; any other text is echoed back as an error.
- `--target <override>` — forces the deployer to use a different
  `DeploymentTarget` enum value for the duration of this dispatch. The
  override reason MUST be non-empty and is logged on the DeployReport.
  Use when the intake's `deployment_target: tbd` placeholder needs to
  be resolved at deploy time without a new `/intake` round-trip.

## Workflow
1. **Gate on QA.** Locate the most recent `qa_report.json` under
   `.soup/runs/<run_id>/`. If `verdict != "APPROVE"`, abort before
   dispatching the deployer. Print the verdict + the path to the
   report. **Running without APPROVE aborts.** The operator must
   resolve findings and re-run `/verify` before `/deploy`.
2. **Gate on intake.** Read `.soup/intake/active.yaml` via
   `IntakeForm.from_yaml`. If missing or invalid, abort.
3. **Resolve target.** Take `--target <override>` when provided; else
   use `form.deployment_target`. If `tbd` and no override, abort with a
   hint: "deployment_target=tbd; re-run /intake or pass --target".
4. **Dispatch `deployer` agent** with:
   - the intake form path,
   - the active `run_id`,
   - the resolved target,
   - the QAReport path,
   - the `deploy_baseline_cmd` (may be `None`),
   - `--target <override>` + reason if applicable.
5. **Capture the DeployReport.** Stream the agent's JSON stdout into
   `.soup/deploy/<run_id>/report.json`. The agent also writes this
   file; the duplicate capture is defensive.
6. **Present verdict.** Table: `status | target | url | smoke | baseline
   | findings`. On `rolled-back` or `regression`, print the rollback
   trail + baseline diff path.
7. **Next step.** On `deployed`, print `gh pr merge` (or
   `az repos pr update --auto-complete true` for ADO) hint. On
   `refused`, print the refusal reason + the command to fix it.

## Output
- DeployReport JSON path under `.soup/deploy/<run_id>/`.
- Target resolved + override reason (if any).
- Deploy URL (public or internal).
- Smoke test exit code + first 200 chars of the response.
- Baseline diff path when `deploy_baseline_cmd` was set.
- Findings table.
- Suggested next step.

## Notes
- **Running without APPROVE aborts.** This is the hard rule that
  keeps `/deploy` from becoming a backdoor around the QA gate. The
  deployer agent also enforces it, but gating here avoids spinning
  up a sonnet subagent just to say "refused".
- **Deployment target is read from the stashed intake, not the
  spec.** Per Constitution Article I, specs describe *what*; the
  stashed `.intake.yaml` carries *how*. The `deployer` agent reads
  `.soup/intake/active.yaml` directly.
- **DeployReport is immutable.** Re-running `/deploy` creates a new
  report under a new `run_id` (or a new suffix under the same run
  when redeploying the same git SHA).
- **`/deploy` never edits application code.** The deployer agent
  scope is CI config only (`files_allowed`:
  `Dockerfile*`, `.github/workflows/**`, `azure-pipelines.yml`,
  `vercel.json`, `docker-compose*.yml`, `deploy/**`). Application
  fixes require a new `/implement` cycle.
- **Rollback is not optional.** Every `rules/deploy/<target>.md`
  documents a rollback mechanism; the deployer attempts it on
  smoke-test failure and records the outcome on the DeployReport.
- **Secrets handling is cross-cutting.** See
  `rules/deploy/secrets.md` — the deployer auto-loads it alongside
  the target-specific rule.
- **Compliance-flag check is belt-and-suspenders.** The
  `IntakeForm._flags_are_consistent` validator rejects
  `internal-only + vercel` and `phi + vercel` at `/intake` time.
  The deployer re-checks at deploy time in case a pre-validator
  intake slipped through.
