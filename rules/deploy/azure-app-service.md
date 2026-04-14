# Deploy target: `azure`

For Streck apps that ship to Azure App Service (Linux, container or
code deploy). Target selector:
`IntakeForm.deployment_target == "azure"`.

## When this applies

- App needs public or VNet-restricted ingress behind Azure Front Door
  / App Gateway.
- `compliance_flags` may include `internal-only` (VNet-only routing),
  `pii`, `phi`, `financial`. `phi` additionally requires a Microsoft
  BAA (standard on Azure commercial) and a customer-owned key scope.
- Slot-based blue/green is the default deploy mechanism.

## Prereqs

- `az login` with a service principal in CI
  (`AZURE_CLIENT_ID` / `AZURE_TENANT_ID` / federated credential via
  GitHub OIDC — see `rules/deploy/github-actions.md`). Never use
  cloud-admin accounts or long-lived client secrets.
- Resource group `rg-<slug>-prod` exists (provisioned by infra, not
  the deployer). The deployer refuses to create it.
- App Service plan `asp-<slug>-prod` on `P1v3` or larger for
  production.

## Image-based deploy (preferred)

Push the image to ACR (`<acr>.azurecr.io/<slug>:<sha>-<branch>`),
then point the staging slot at it:

```bash
az acr login -n <acr>
docker tag "$IMAGE_LOCAL" "<acr>.azurecr.io/$APP:$SHA-$BRANCH"
docker push "<acr>.azurecr.io/$APP:$SHA-$BRANCH"

az webapp config container set \
  --name "<app>-prod" \
  --resource-group "rg-<app>-prod" \
  --slot staging \
  --docker-custom-image-name "<acr>.azurecr.io/$APP:$SHA-$BRANCH" \
  --docker-registry-server-url "https://<acr>.azurecr.io"
```

Prefer Managed Identity for ACR pulls (no registry password in app
settings): `az webapp config set --generic-configurations
'{"acrUseManagedIdentityCreds": true}'`.

## Code-based deploy (fallback)

For projects that cannot yet ship a container:

```bash
az webapp deployment source config-zip \
  --name "<app>-prod" --resource-group "rg-<app>-prod" \
  --slot staging --src dist.zip
```

Only acceptable as a transitional step; image-based is the target
state.

## Blue/green via slot swap

```bash
# warm the staging slot (App Service does a synthetic GET /)
sleep 30

# run smoke against the staging hostname
curl -fsS "https://<app>-prod-staging.azurewebsites.net/health"

# swap
az webapp deployment slot swap \
  --name "<app>-prod" --resource-group "rg-<app>-prod" \
  --slot staging --target-slot production
```

The swap is near-instant (app settings + hostname flip). Rollback is
a second `slot swap` with source/target reversed — the deployer
preserves the previous production as staging for exactly one deploy.

## App settings + connection strings

All non-secret config in **app settings**; all secrets in **Key
Vault** with Managed Identity references:

```bash
az webapp config appsettings set \
  --name "<app>-prod" --resource-group "rg-<app>-prod" \
  --slot staging \
  --settings \
    LOG_LEVEL=info \
    POSTGRES_HOST="@Microsoft.KeyVault(SecretUri=https://<kv>.vault.azure.net/secrets/postgres-host/)" \
    POSTGRES_PASSWORD="@Microsoft.KeyVault(SecretUri=https://<kv>.vault.azure.net/secrets/postgres-password/)"
```

`Slot setting` checkbox (sticky) for environment discriminators
(`APP_ENV=production`); leave sticky OFF for per-deploy values so the
swap carries them.

## Smoke test

```bash
curl -fsS "https://<app>-prod.azurewebsites.net/health"
```

Against the production hostname after the swap. Non-200 → immediate
re-swap (rollback).

## Rollback

```bash
az webapp deployment slot swap \
  --name "<app>-prod" --resource-group "rg-<app>-prod" \
  --slot production --target-slot staging
```

Slot swap is the rollback primitive. The deployer logs both the
forward and reverse swap commands on the DeployReport.

## Compliance notes

- `internal-only`: configure the App Service with
  `--vnet-route-all-enabled true` and a private endpoint; disable
  public access (`az webapp update ... --public-network-access
  Disabled`).
- `phi` / `pii`: mandatory Key Vault + Managed Identity for secrets;
  app-level encryption key in customer-managed-key scope. Log
  forwarding to the Streck-authorised SIEM (App Insights alone is
  insufficient for `phi`).
- `financial`: same as `phi` + enable diagnostic settings to an
  append-only storage account.

## Verifier

`just deploy-verify` runs:

- `az webapp config show ...` on the staging slot, greps for the
  expected `ACR_IMAGE` + app settings.
- `az webapp log tail` for 30s post-swap, asserts no `ERROR`-level
  entries.
- `trivy image` on the ACR image tag (same gate as internal-docker).
