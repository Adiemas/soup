# Deploy target: `internal-docker`

For Streck apps that ship to the internal Docker host (behind VPN, no
public ingress). Target selector:
`IntakeForm.deployment_target == "internal-docker"`.

## When this applies

- App is accessed over the Streck corporate VPN only — no public DNS.
- `compliance_flags` may include `internal-only`, `lab-data`, or
  `pii`. All three are compatible with this target; `public` and
  this target are mutually inconsistent (intake validator should
  already have caught it).
- Image ships to the internal registry (`registry.internal.streck/`);
  the deploy host pulls from there.

## Image build

Multi-stage `Dockerfile.prod` required. The dev `Dockerfile` the
template ships is not acceptable for prod (no non-root user, no
healthcheck, no OCI labels). The deployer emits `Dockerfile.prod`
alongside the dev one — it does **not** overwrite.

Required properties:

- Multi-stage: `builder` stage pulls deps; `runtime` stage copies
  only what runs.
- Non-root runtime user: `RUN useradd -m -u 10001 app; USER app`.
- `HEALTHCHECK CMD curl -fsS http://127.0.0.1:${PORT:-8000}/health || exit 1`
  — 30s interval, 10s timeout, 3 retries.
- OCI labels: `org.opencontainers.image.source`, `.revision`,
  `.created`, `.version` populated from git SHA + branch + build
  timestamp.
- Tag format: `registry.internal.streck/<app_slug>:<sha>-<branch>`.
  Always also tag `:<sha>` so rollback can reference a stable tag.

## Registry push

```bash
docker login registry.internal.streck -u "$DOCKER_USER" -p "$DOCKER_PASS"
docker build -f Dockerfile.prod -t "$IMAGE_REF" -t "registry.internal.streck/$APP:$SHA" .
docker push "$IMAGE_REF"
docker push "registry.internal.streck/$APP:$SHA"
```

Creds come from the deploy host's env; never from `.env`. See
`rules/deploy/secrets.md`.

## Deploy mechanism

SSH into the internal docker host and apply a compose override:

```bash
ssh deploy@docker-host-01.internal.streck \
    "cd /opt/apps/$APP && \
     docker compose -f docker-compose.yml -f docker-compose.prod.yml \
       pull && \
     docker compose -f docker-compose.yml -f docker-compose.prod.yml \
       up -d --remove-orphans"
```

The override file (`docker-compose.prod.yml`) sets:

- `image: registry.internal.streck/<app>:<sha>-<branch>` (no
  `build:` — prod uses the registry, never rebuilds on the host).
- `restart: unless-stopped`.
- `logging.driver: journald` so `journalctl -u docker -t $APP` tails
  the container — matches the host's existing `systemd` unit.
- `labels: streck.app=<slug>`, `streck.env=prod` so the host's
  Splunk forwarder filters correctly.

A systemd `app-<slug>.service` unit on the host wraps the compose
bring-up so a host reboot resurrects the app. The deployer does NOT
modify the unit; it is owned by the docker-host provisioner.

## Smoke test

```bash
curl --cacert /etc/ssl/streck-internal-ca.pem \
     -fsS "https://<slug>.internal.streck/health"
```

Expected: HTTP 200 JSON body matching the spec's
`#health-contract` section. Non-200 → rollback.

## Rollback

Previous-image-tag rollback. The compose override on the host is
updated in place to pin the prior `:<sha>` tag:

```bash
ssh deploy@docker-host-01.internal.streck \
    "cd /opt/apps/$APP && \
     docker compose -f docker-compose.yml -f docker-compose.prod.yml \
       pull <slug>:<previous-sha> && \
     docker compose up -d <service>"
```

`<previous-sha>` is read from the `:previous` symbolic tag the
deployer advances after a successful smoke test. On rollback, the
`:previous` tag is NOT advanced; this keeps the next deploy able to
roll back to the last-known-good.

## VPN + ingress

Ingress is the internal Traefik (or nginx) in front of the docker
host; routing is `<slug>.internal.streck`. DNS is managed out of
band. The deployer does not touch DNS or the ingress — if the route
is missing, refuse with a finding pointing at the
`docs/runbooks/internal-docker-ingress.md` (author a runbook if one
does not exist).

## Compliance notes

- `internal-only`: this target is its natural home. No additional
  action.
- `lab-data`: audit log shipping is mandatory. The compose override
  must include the `fluent-bit` sidecar that forwards to the Streck
  SIEM. Deployer asserts the sidecar is declared before deploying.
- `pii` / `phi`: refuse on `phi` without a Streck-signed BAA
  attached to the compose override (`streck.baa=<id>` label).

## Verifier

`just deploy-verify` on the source repo runs a lint pass against
`Dockerfile.prod` and the compose override:

- `hadolint Dockerfile.prod` (must pass).
- `docker compose -f docker-compose.yml -f docker-compose.prod.yml config`
  (must parse).
- `trivy image --exit-code 1 --severity CRITICAL,HIGH $IMAGE_REF`
  (no critical/high CVEs by default; `compliance_flags: public`
  tightens to `--severity CRITICAL,HIGH,MEDIUM`).
