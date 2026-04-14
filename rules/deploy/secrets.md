# Deploy rule: secrets

Cross-cutting secrets hygiene for every `deployment_target`. The
deployer auto-loads this rule alongside the target-specific rule.
Author: deployer agent. Reviewer: security-scanner on every `/verify`.

## Iron law

**NEVER commit `.env`, `.env.local`, `.env.production`, or any
terraform state file (`*.tfstate`, `*.tfstate.backup`).** Only
`.env.example` (key names + placeholder values, no real values) is
committed. The repo's `.gitignore` ships with these entries; the
deployer refuses to deploy if any of the forbidden files are present
in the tracked tree:

```bash
git ls-files | grep -E '^(\.env($|\.local|\.production)|.*\.tfstate)$' && exit 1
```

The `security-scanner` already runs gitleaks on every `/verify`; the
deployer re-checks as a belt-and-suspenders step.

## Azure Key Vault

Production secrets in Azure targets live in Key Vault
(`kv-<app>-prod`). App Service + Container Apps consume them via the
`@Microsoft.KeyVault(SecretUri=...)` reference syntax so the runtime
never sees the raw secret, just the Managed Identity pull. See
`rules/deploy/azure-app-service.md` for the reference format.

Rotation cadence:

- `DATABASE_URL` / `_PASSWORD`: 90 days.
- API keys for third-party services: per the upstream vendor's
  recommendation, never longer than 180 days.
- OIDC federated credentials: no rotation needed (short-lived by
  design).

Access policies: **least privilege**. App's Managed Identity gets
`get` on secrets only — no `list`, no `set`. The CI pipeline's
service connection gets `set` for secret-seeding scripts only if the
repo owns secret-seeding; otherwise the infra team owns seeding
out-of-band.

## GitHub Secrets

Repo-level secrets (preferred over org-level for scoping):
`Settings → Secrets and variables → Actions`. Used by GitHub Actions
jobs. Naming: `UPPER_SNAKE_CASE`, prefixed by purpose
(`AZURE_CLIENT_ID`, `VERCEL_TOKEN`, `INTERNAL_DEPLOY_SSH_KEY`).

Environment-scoped secrets for production jobs:
`Settings → Environments → production → Secrets`. Pair with required
reviewers so the secrets are only available after an approval —
defense in depth against a compromised PR that tries to exfiltrate.

Rotation cadence: 90 days for every long-lived token. Automate via
`gh secret set` in a scheduled workflow where the upstream supports
programmatic rotation. Manual rotations leave a calendar entry in
the team's ops calendar; no silent extensions.

## ADO secure files + variable groups

See `rules/deploy/ado-pipelines.md` for the pipeline wiring. Storage
rules:

- **Key Vault-linked variable groups** for ordinary secrets.
- **Secure files** for binary artefacts (GPG keys, certificates).
- **No secrets in YAML.** A secret in `azure-pipelines.yml`,
  `azure-pipelines-*.yml`, or any `.azuredevops/` file is a
  BLOCK-level security finding.

Rotation cadence: same as GitHub Secrets (90 days baseline).

## Vercel env

- `NEXT_PUBLIC_*` prefix means the value is inlined at build time
  and shipped to every client. **Never put a secret behind
  `NEXT_PUBLIC_*`.** Code review blocks on this.
- Non-public env vars live in Vercel's dashboard (or `vercel env
  add`) and are exposed to server-side code only (Server Components,
  Route Handlers, Server Actions).
- `vercel env pull .env.local --environment preview` is the
  dev-time consumption pattern. `.env.local` is gitignored; never
  committed.

Rotation cadence: 90 days.

## Internal docker + on-prem

Secrets on the docker host live in the Streck internal vault (HashiCorp
Vault in most regions, CyberArk in EU regions). The deploy host pulls
secrets at container startup via `vault agent` and writes them to a
tmpfs mount the container reads. The repo's `docker-compose.prod.yml`
MUST reference the tmpfs mount, never an env-var literal.

Rotation cadence: 90 days for database credentials; 30 days for
infrastructure admin accounts.

## What to do when a secret leaks

1. **Rotate first, file later.** The moment a leak is detected
   (gitleaks alert, accidental commit, revoked access not taken),
   rotate the secret at the source.
2. **Invalidate the old value.** In the target system (Key Vault,
   GitHub Secrets, Vercel, Vault) — not just in the repo.
3. **Rewrite history.** `git filter-repo` to purge the leak from the
   repo's history; force-push requires an exception approval
   (`CONSTITUTION.md §VI`).
4. **Open an incident runbook entry** under
   `docs/runbooks/secret-leak-<slug>.md` with the rotation timeline
   + blast radius.
5. **Re-scan.** Run `security-scanner` on the purged history to
   confirm no other leaks were adjacent.

The deployer refuses to deploy if any of its input files
(`.github/workflows/**`, `azure-pipelines.yml`, `vercel.json`,
compose files) contain a literal matching the gitleaks patterns —
even if the leaking file is not yet committed.

## What NOT to do

- Do not paste a secret into a PR description, commit message, or
  issue comment "for convenience." The gitleaks action catches
  commits, not prose — but the security-scanner reviews every
  `/verify` diff and will block.
- Do not grant `list` or `*` on Key Vault to a runtime identity —
  only `get` on specific secrets. A runtime that can list secrets
  is one misconfiguration away from exfiltrating all of them.
- Do not store long-lived service-principal passwords when a
  federated credential (OIDC / Workload Identity) is available.
- Do not reuse the same secret across `dev` / `staging` / `prod`.
  Rotation means "rotate in every environment"; reuse doubles the
  blast radius without halving the work.
