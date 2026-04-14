# Deploy target wiring: Azure DevOps Pipelines

CI/CD skeleton for repos hosted on Azure DevOps. Parallel to
`rules/deploy/github-actions.md`; the deployer chooses based on the
parent repo host (inferred from `origin` URL). Edits are scoped to
`azure-pipelines.yml` + `.azuredevops/pipelines/*.yml`.

## Pipeline shape

`azure-pipelines.yml` — triggered on merge to `main`:

```yaml
trigger:
  branches:
    include: [main]

pr:
  branches:
    include: ['*']

variables:
  - group: <app>-prod        # variable group (see "Variable groups")
  - name: imageTag
    value: $(Build.SourceVersion)

stages:
  - stage: CI
    jobs:
      - job: test
        pool: { vmImage: ubuntu-latest }
        steps:
          - task: UsePythonVersion@0
            inputs: { versionSpec: '3.12' }
          - script: just init
          - script: just lint
          - script: just test

  - stage: Deploy
    dependsOn: CI
    condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main'))
    jobs:
      - deployment: deploy
        environment: '<app>-prod'            # triggers approvals
        pool: { vmImage: ubuntu-latest }
        strategy:
          runOnce:
            deploy:
              steps:
                - template: .azuredevops/pipelines/deploy-$(deploymentTarget).yml
```

`deploymentTarget` is a variable sourced from the intake
(`IntakeForm.deployment_target`) via a pre-pipeline step — or
overridden at queue time.

## Approvals + environment gates

Environments (`<app>-prod`) carry the approval gates, not the pipeline
YAML. Configure once per environment via the ADO UI (or
`az devops`):

- **Checks → Approvals:** at least one approver; two for
  `phi` / `financial`. Approvers are team leads, not the author.
- **Checks → Business hours:** optional; restrict prod deploys to
  09:00–17:00 Streck time when `compliance_flags: lab-data` to
  avoid conflicting with lab operations.
- **Checks → Branch control:** only `refs/heads/main` can deploy to
  `<app>-prod`.
- **Checks → Exclusive lock:** one deploy at a time (prevents two
  merges from stepping on each other mid-swap).

## Variable groups

All non-secret config in a linked variable group
(`<app>-prod-config`). All secrets in a **Key Vault-linked**
variable group (`<app>-prod-secrets`) so secrets come from Azure Key
Vault rather than being stored in ADO:

```bash
# Link a Key Vault variable group
az pipelines variable-group create \
  --name "<app>-prod-secrets" \
  --authorize true \
  --variables \
    DATABASE_URL=@$(KV:database-url) \
    API_KEY=@$(KV:api-key)
```

The `@$(KV:...)` notation is the ADO convention for Key Vault-backed
values. The deployer refuses to deploy if a secret-looking variable
(`_KEY`, `_PASSWORD`, `_TOKEN`, `_SECRET`) lives in the non-secret
group; the `security-scanner` already runs a pre-commit gate, but
the deployer double-checks at pipeline-author time.

## OIDC-equivalent (Workload Identity)

ADO supports **Workload Identity Federation** (the ADO equivalent of
GitHub OIDC) — use it instead of service-principal passwords:

```yaml
- task: AzureCLI@2
  inputs:
    azureSubscription: '<service-connection-name>'   # WIF-backed
    scriptType: bash
    scriptLocation: inlineScript
    inlineScript: |
      az webapp deployment slot swap \
        --name "<app>-prod" --resource-group "rg-<app>-prod" \
        --slot staging --target-slot production
```

Create the service connection with **"Workload Identity federation"**
auth type, not "Service principal (automatic)" (which uses a
short-lived cert) or "Service principal (manual)" (which uses a
long-lived password — reject at review).

## Secure files

For assets that cannot live in Key Vault (e.g. a GPG key for signing
releases, a client certificate for an upstream API), use ADO
**secure files**:

```yaml
- task: DownloadSecureFile@1
  name: signing
  inputs:
    secureFile: 'release-signing.key'

- script: gpg --import $(signing.secureFilePath)
```

Rotation: same cadence as the secret the file represents (see
`rules/deploy/secrets.md`).

## Branch policies (parallel to GitHub branch protection)

On `main`:

- Require minimum reviewer count (1 default; 2 for `phi` /
  `financial`).
- Require build validation (`ci` stage green).
- Require linked work items (matches Constitution I work-item
  threading).
- Auto-complete after all policies pass — deploy stage runs next.

Managed by `ado-agent` via `az repos policy create` when the
deployer opens the first PR.

## Pipeline templates

Target-specific deploy steps live in
`.azuredevops/pipelines/deploy-<target>.yml` to keep the top-level
`azure-pipelines.yml` readable:

- `deploy-internal-docker.yml` — `docker push` + SSH apply (see
  `rules/deploy/internal-docker.md`).
- `deploy-azure.yml` — `az webapp` slot swap (see
  `rules/deploy/azure-app-service.md`).
- `deploy-vercel.yml` — `npx vercel --prod` (see
  `rules/deploy/vercel.md`; note refusals for `internal-only` /
  `phi`).

The deployer writes these templates on first deploy; subsequent
deploys only touch the `azure-pipelines.yml` top-level when the
variable group name or environment name changes.
