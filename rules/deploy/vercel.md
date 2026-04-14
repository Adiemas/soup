# Deploy target: `vercel`

For Streck apps that ship to Vercel (Next.js and Node functions).
Target selector: `IntakeForm.deployment_target == "vercel"`.

## When this applies

- App is **public-edge** by design (marketing, customer-facing SaaS,
  public API). Vercel is a public CDN; do not use for internal-only
  apps. The intake validator rejects
  `internal-only + vercel` and `phi + vercel` at form time; the
  deployer re-checks at deploy time.
- Stack is typically `nextjs-app-router` (but any static-plus-
  functions layout works).

## Hard refusals

- `compliance_flags` contains `internal-only` → refuse. Vercel is a
  public-edge platform; use `azure` with private endpoint or
  `internal-docker` instead.
- `compliance_flags` contains `phi` → refuse. Vercel does not sign
  BAAs by default. A committed-for-signature BAA does not override
  this rule; the path is `azure` (Microsoft BAA) or
  `internal-docker`.

## Deploy mechanism

Prefer the harness skill when available:

- `vercel:deploy` with `prod` argument for production;
  default (no arg) for preview.
- `vercel:env` for environment variable sync (see "Env" below).
- `vercel:deployments-cicd` when wiring a GitHub Actions workflow.

Raw CLI fallback (when the skill is not exposed):

```bash
# Production
npx vercel --prod --token "$VERCEL_TOKEN" --yes

# Preview (every PR)
npx vercel --token "$VERCEL_TOKEN" --yes
```

Project link (one-time per clone):

```bash
npx vercel link --yes --token "$VERCEL_TOKEN" \
    --project "$VERCEL_PROJECT_NAME" \
    --org "$VERCEL_ORG_ID"
```

The deployer refuses to re-link an already-linked project; the
`.vercel/project.json` file is the source of truth.

## Preview URLs on PR

Every non-main branch push creates a preview URL via
`vercel --no-prod` (or `vercel:deploy` without `prod`). The deployer
posts the URL as a PR comment so reviewers can test the branch
against live data before merge. See
`rules/deploy/github-actions.md` for the workflow that calls
`vercel` on every PR event.

The comment format (the deployer writes this via the
`github-agent`):

```
Preview: <https://<slug>-<hash>-<team>.vercel.app>
SHA: `<sha>`
Build log: <https://vercel.com/<team>/<project>/<deployment-id>>
```

## Env var management

Sync once per environment via `vercel env pull`:

```bash
# Local dev: pull preview env into .env.local
npx vercel env pull .env.local --environment preview

# CI: pull production into .env.production for build-time inlining
npx vercel env pull .env.production --environment production
```

Add/remove in Vercel:

```bash
npx vercel env add DATABASE_URL production
npx vercel env rm STALE_VAR production
```

Rule: `.env.local` and `.env.production` are **gitignored**. Only
`.env.example` is committed. See `rules/deploy/secrets.md`.

Public-prefixed vars (`NEXT_PUBLIC_*`) are inlined at build time —
they are shipped to every client. Keep them for non-secret config
(feature flags, public API URLs). Secrets MUST NOT have the
`NEXT_PUBLIC_` prefix.

## Fluid Compute note

As of Next 16 / Vercel 2026, **Fluid Compute** is the default
runtime for Server Components and Route Handlers — long-running
functions share a warm pool with connection reuse. This changes
cold-start economics vs classic Serverless Functions. No deployer
action is required (it is a platform default), but two
implications matter for rule authoring:

- In-process globals (DB pools, cached clients) survive between
  requests within a compute unit. Design DB access accordingly
  (prefer pooled clients; avoid per-request client construction).
- `export const runtime = "edge"` still opts the handler into the
  edge runtime (no Node APIs, no pooling). Pick per-handler.

See `vercel:vercel-functions` skill for Fluid Compute depth.

## Smoke test

```bash
curl -fsS "https://<production-hostname>/api/health"
```

Use the canonical production hostname (configured via `vercel
domains add`), not the auto-generated `*.vercel.app` alias — the
alias rotates.

## Rollback

Vercel's `rollback` command flips the production alias to the prior
deployment:

```bash
npx vercel rollback --yes --token "$VERCEL_TOKEN"
```

Rollback is near-instant (alias flip). The deployer records the
pre-deploy deployment ID and the post-rollback deployment ID on the
DeployReport so auditors can follow the alias chain.

## Verifier

- `npx vercel inspect <url>` confirms the deployment is `READY` and
  not `ERROR`/`BUILDING`.
- `curl -fsS https://<hostname>/api/health` smoke.
- No image CVE scan step (Vercel builds run on Vercel; the platform
  handles base image patching). The code-level
  `security-scanner` pass already ran at `/verify` time.
