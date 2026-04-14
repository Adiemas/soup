# Deploy target wiring: GitHub Actions

CI/CD skeleton for repos whose parent org is on GitHub. Reused by
every `deployment_target` except when the target-specific rule
explicitly calls for ADO. The deployer writes
`.github/workflows/deploy.yml` if absent; edits are scoped to that
file + `.github/workflows/ci.yml`.

## Workflow shape

`.github/workflows/deploy.yml` — triggered on `push` to `main` or
manual `workflow_dispatch`:

```yaml
name: deploy
on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      target:
        description: "deployment_target override"
        required: false
        default: ""

permissions:
  id-token: write        # OIDC for cloud auth
  contents: read
  pull-requests: write   # for preview-url comment

concurrency:
  group: deploy-${{ github.ref }}
  cancel-in-progress: false

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production   # triggers required reviewers
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }

      - name: Read intake
        id: intake
        run: |
          python -c "from schemas.intake_form import IntakeForm; \
            f = IntakeForm.from_yaml('.soup/intake/active.yaml'); \
            print(f'target={f.deployment_target}')" >> $GITHUB_OUTPUT

      - name: Resolve target
        id: target
        run: |
          echo "value=${{ inputs.target || steps.intake.outputs.target }}" \
            >> $GITHUB_OUTPUT

      # Target-specific blocks below. Only one runs per job.

      - name: Azure login (OIDC)
        if: steps.target.outputs.value == 'azure'
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

      - name: Deploy (azure)
        if: steps.target.outputs.value == 'azure'
        run: ./.github/workflows/deploy-azure.sh

      - name: Deploy (vercel)
        if: steps.target.outputs.value == 'vercel'
        run: npx vercel --prod --token "$VERCEL_TOKEN" --yes
        env:
          VERCEL_TOKEN: ${{ secrets.VERCEL_TOKEN }}

      - name: Deploy (internal-docker)
        if: steps.target.outputs.value == 'internal-docker'
        run: ./.github/workflows/deploy-internal-docker.sh
        env:
          DEPLOY_SSH_KEY: ${{ secrets.INTERNAL_DEPLOY_SSH_KEY }}
```

## OIDC for cloud auth

Long-lived cloud credentials in GitHub Secrets are deprecated. Use
**federated credentials** so GitHub Actions mints a short-lived OIDC
token:

- **Azure:** `azure/login@v2` with `client-id` + `tenant-id` from
  secrets; no client secret. Configure the App Registration with a
  federated credential scoped to
  `repo:<org>/<repo>:ref:refs/heads/main`.
- **AWS:** `aws-actions/configure-aws-credentials@v4` with
  `role-to-assume` — no access-key pair.
- **GCP:** `google-github-actions/auth@v2` with Workload Identity
  Federation.

Do not check a service-principal password into `secrets.` —
fail the workflow-write review if you see one.

## Branch protection gating

On `main` (and any production branch), enable via repo settings:

- Require pull request reviews (≥1; ≥2 for `phi` / `financial`
  flags).
- Require status checks: `ci / test`, `ci / typecheck`,
  `security / gitleaks`, `security / trivy-image` (when applicable).
- Require deployment to the `production` environment — triggers the
  required-reviewer gate before the deploy job runs.
- Require signed commits when `compliance_flags` includes any of
  `pii`, `phi`, `financial`.

The `github-agent` flips these via `gh api` when the deployer opens
the first PR; a prior configuration is not overwritten.

## PR preview deploys

`.github/workflows/preview.yml` — triggered on `pull_request`:

```yaml
on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  preview:
    if: github.event.pull_request.head.repo.full_name == github.repository
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Vercel preview
        run: |
          url=$(npx vercel --token "$VERCEL_TOKEN" --yes)
          echo "url=$url" >> $GITHUB_OUTPUT
        env:
          VERCEL_TOKEN: ${{ secrets.VERCEL_TOKEN }}
```

Pair with the `github-agent`'s preview-comment post; the deployer
does not post PR comments itself.

## CI skeleton (lint + test)

`.github/workflows/ci.yml` — always runs on PR:

```yaml
name: ci
on: [pull_request, push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5      # or setup-node@v4
        with: { python-version: '3.12' }
      - run: just init
      - run: just lint
      - run: just test
  gitleaks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: gitleaks/gitleaks-action@v2
```

The `ci.yml` skeleton is identical across templates — the deployer
never edits it after first-write; updates go via
`/soup-init --refresh-ci` (out of scope for this iteration).
