# Cycle 1 — Critic Review: Completeness, Consistency, Coherence

_Reviewer: independent senior AI engineer. Scope: `C:\Users\ethan\AIEngineering\soup\` as of 2026-04-14._

The framework is structurally well-formed: 16 pillars have at least some physical artifact, schemas are strict and validated, and hooks are more than stubs. But several contract seams do not close. The biggest risks are a broken RAG CLI surface (scripts that agents invoke do not exist as CLIs), justfile recipes routed to Typer subcommands that are not defined, and a `/verify` gate whose assembler in `orchestrator/cli.py` is a stub.

## 1. Pillar coverage matrix (DESIGN.md §2)

| # | Pillar | Files inspected | Verdict | Evidence |
|---|---|---|---|---|
| 1 | Skills | `.claude/skills/{tdd,agentic-rag-research,spec-driven-development,meta-prompting,cli-wrapper-authoring,brainstorming,dispatching-parallel-agents,executing-plans,requesting-code-review,subagent-driven-development,systematic-debugging,using-git-worktrees,verification-before-completion,writing-plans}/SKILL.md` | Done | All 14 skill dirs each contain one `SKILL.md` with YAML frontmatter + iron-law body. |
| 2 | Agent roster | `.claude/agents/*.md` (20 files) | Done | DESIGN promises 20 specialists; directory has 20 agent .md files all with name/description/tools/model frontmatter. |
| 3 | Commands | `.claude/commands/*.md` (14 files) | Done | All 14 commands named in DESIGN §7 exist. |
| 4 | Hooks | `.claude/hooks/{session_start,user_prompt_submit,pre_tool_use,post_tool_use,subagent_start,stop}.py` + `settings.json` | Done | All 6 hooks exist as executable python, all 6 referenced in `settings.json` under correct event names. |
| 5 | Rules | `rules/{global,python,dotnet,react,typescript,postgres}/*.md` | Done | 6 stack subdirs each with at least one `.md`. Pre-tool-use hook routes by extension correctly. |
| 6 | Schemas | `schemas/{execution_plan,qa_report,spec,task,agent_log}.py` | Done | Strict Pydantic v2 with `extra="forbid"`. `ExecutionPlanValidator` enforces DAG + roster membership. |
| 7 | Orchestrator | `orchestrator/{orchestrator,agent_factory,waves,state,meta_prompter,cli}.py` | Done | `Orchestrator.run()` computes waves, spawns via `agent_factory.spawn`, runs verify, persists state, appends `logging/experiments.tsv`. |
| 8 | Meta-prompter | `orchestrator/meta_prompter.py` | Done | Loads roster from library.yaml, opus call with ephemeral prompt caching, 3-retry self-correction loop. |
| 9 | RAG | `rag/{client,ingest,search,mcp_server,sources/*}.py` | Partial | Core Python API is complete; CLI wiring is broken — see §2. |
| 10 | CLI wrappers | `cli_wrappers/{ado,docker,dotnet,gh,git,psql}.py` | Done | All five wrappers + psql present (justfile for `python-fastapi-postgres` uses `python -m cli_wrappers.psql migrate-up`). |
| 11 | Templates | `templates/{python-fastapi-postgres,dotnet-webapi-postgres,react-ts-vite,fullstack-python-react}` | Partial | All 4 exist with CLAUDE.md + README + justfile. React template lacks migrations (correct). See §4 for dotnet gaps. |
| 12 | Justfile | `justfile` | Partial | All recipes present; many call Typer subcommands that are not defined (§5). |
| 13 | Logging | `logging/agent-runs/` (empty dir), hook JSONL writes, `experiments.tsv` via Orchestrator | Done | Session JSONL scheme consistent across session_start, post_tool_use, pre_tool_use, stop. |
| 14 | Library catalog | `library.yaml` | Done | 13 skills + 20 agents listed. Matches DESIGN §2. |
| 15 | Worktrees | `.soup/worktrees/` exists; no CLI helper | Stub | Directory exists; `just worktree`/`worktree-rm` route to CLI commands that do not exist (§5). |
| 16 | Memory | `CLAUDE.md`, `MEMORY.md`, `.soup/memory/` | Done | All three present. Dream-consolidation explicitly deferred (DESIGN §10). |

## 2. Contract mismatches

**Critical:**

1. **`rag/search.py` and `rag/ingest.py` are not CLIs.** Only `rag/mcp_server.py` has a `__main__`. Yet they are invoked as scripts across the stack:
   - `.claude/hooks/subagent_start.py` line 78: `subprocess.run([sys.executable, str(script), query], …)`.
   - `.claude/agents/rag-researcher.md` line 19: `python rag/search.py --query <q> --top-k 8 --filter <scope>`.
   - `.claude/agents/docs-ingester.md` line 22: `python rag/ingest.py --source <descriptor> --tags <csv>`.
   - `justfile` lines 90, 95, 103: `python -m rag.search "{{query}}"`, `python -m rag.ingest "…"`, `python -m rag.ingest --reindex-all`.
   None of these work; both files expose only class-based APIs (`Searcher`, `Ingester`) that require a constructed `LightRagClient`.

2. **`orchestrator/cli.py` `soup verify` is a printing stub.** Lines 144-157 print `"qa-orchestrator wiring pending. Run the /verify Claude Code command instead."` but DESIGN §4 and Constitution Article IV promise a programmatic QA gate. `justfile verify:` routes `python -m orchestrator.cli verify --ref HEAD` — `--ref` is not even a defined option.

3. **`soup ingest` / `soup search` commands call non-existent module attributes.** `orchestrator/cli.py` lines 167-168 and 179-180 look up `rag.ingest` / `rag.ingest_source` / `rag.search` / `rag.query` as callables on the `rag` package. But `rag/__init__.py` only re-exports **classes** (`IngestReport, LightRagClient, Retrieval, SearchMode`). `_resolve_rag_callable` will always hit the "missing callable" branch and exit 2.

**High:**

4. **qa-orchestrator dispatches `verifier` but both DESIGN and `/verify` command refer to `test-runner`.** DESIGN §4 says "code-reviewer + security-scanner + test-runner in parallel"; `/verify` command body (line 17) says "verifier — runs all declared `verify_cmd`s … delegate the `test-runner` role to `verifier`". The roster has `verifier` but no `test-runner` agent. This is reconciled in the qa-orchestrator agent file, but DESIGN.md §2 row 4 and §3 still call it `test-runner`, which is misleading.

5. **MultiEdit tool not declared in any agent frontmatter.** `settings.json` PreToolUse matcher is `"Edit|Write|MultiEdit"` and `stop.py` `WRITE_TOOLS = {"Edit","Write","MultiEdit"}`. All 20 agents list only `Edit, Write` in their tools. Agents cannot actually invoke MultiEdit, so the hook's MultiEdit branch is dead code.

6. **`AskUserQuestion` tool is not allow-listed anywhere.** Commands `clarify.md`, `constitution.md`, `install.md` say "Use AskUserQuestion …". `AskUserQuestion` is not listed in any agent's `tools:` frontmatter and not in `settings.json` permissions. HITL flows will fail or silently no-op.

7. **Meta-prompter rejects agents not in library.yaml, but `test-runner` is referenced in DESIGN flow.** If a future template names `test-runner` in a plan, `ExecutionPlanValidator` will reject it with `"step … references agent 'test-runner' which is not in the roster"`.

8. **Command filename "soup-init" vs docs "new template".** `.claude/commands/soup-init.md` exists, but `just new template name` exists in justfile. Users following DESIGN §9 run `just new`; users in Claude Code run `/soup-init`. Both route to different CLI subcommands (`just new` → `python -m orchestrator.cli new "…"`, which does not exist) — misalignment.

**Medium:**

9. **`rag_queries` contract never executed by orchestrator.** DESIGN §4 says `SessionStart hook ← load .env, prime codebase`; `subagent_start hook ← inject rules (by ext) + RAG context`. `subagent_start.py` reads only `SOUP_RAG_QUERIES` from env — `agent_factory.py` `_build_invocation()` passes `--rag-queries` to the `claude` CLI (line 98) but never sets `SOUP_RAG_QUERIES`. The per-step `rag_queries` on a TaskStep will not materialize inside the subagent.

10. **Constitution Article VIII cost discipline contradicts agent list.** Article VIII.3 limits opus to `orchestrator, meta-prompter, architect, sql-specialist`. The agent file `sql-specialist.md` sets `model: opus` — OK. But DESIGN §6 also lists `sql-specialist` with model `opus` — consistent. No issue; just confirming alignment.

11. **`/install` invokes `just install` which itself calls `python -m orchestrator.cli install {{mode}}`.** The `install` Typer command is not defined in `orchestrator/cli.py`. Will exit `no_args_is_help=True` → usage error.

12. **Typer CLI has 6 commands: `plan, run, status, verify, ingest, search`.** Justfile and commands rely on many more: `go, quick, new, worktree, worktree-rm, logs, doctor, clean, install`. None exist.

## 3. Skill/agent alignment

- **Skills in library.yaml (13)** vs **SKILL.md present (14)**. Catalog lists: brainstorming, tdd, systematic-debugging, verification-before-completion, writing-plans, executing-plans, subagent-driven-development, dispatching-parallel-agents, agentic-rag-research, spec-driven-development, meta-prompting, cli-wrapper-authoring. Directory adds `using-git-worktrees` and `requesting-code-review` that are NOT registered in `library.yaml`. DESIGN §5 explicitly lists both under "Coordination (flexible)." The catalog is missing two canonical skills promised by DESIGN.
- **Agents in library.yaml (20)** vs **agent .md files (20, plus one stray at `.claude/agents/utility/researcher.md` — 21 on disk)**. `researcher.md` under `utility/` is NOT named by DESIGN §6, NOT in `library.yaml`, and NOT referenced by any command. Dead file.
- **Name typos:** none found. All library.yaml agent names exactly match filenames.
- **No test-runner agent,** although referenced by name in DESIGN §4 and `/verify.md`. `qa-orchestrator.md` papers over by aliasing to `verifier` — inconsistent.

## 4. Template coverage

| Template | CLAUDE.md | README | justfile | Migrations | Tests | Runnable (`docker-compose up`) |
|---|---|---|---|---|---|---|
| python-fastapi-postgres | yes | yes | yes | `0001_init.up/down.sql` | `tests/test_health.py` | yes — has `docker-compose.yml`, `Dockerfile`, `pyproject.toml` |
| dotnet-webapi-postgres | yes | yes | yes | **only `Migrations/README.md`** (empty dir — EF expects generated files) | `YourApi.Tests/HealthControllerTests.cs` | yes — has `docker-compose.yml`, `Dockerfile` |
| react-ts-vite | yes | yes | yes | n/a (frontend, correct) | `src/__tests__` exists but no visible tests in listing (only setup dir) | partial — has `Dockerfile` + `nginx.conf` but **no `docker-compose.yml`** (no backend to compose) |
| fullstack-python-react | yes | yes | yes | `backend/migrations/0001_init.up/down.sql` | `backend/tests/test_api.py` + `frontend/src/__tests__` | yes — top-level `docker-compose.yml` + both Dockerfiles |

Gaps: dotnet template ships an empty `Migrations/` (placeholder README only) — docker-compose up will start but `dotnet ef database update` will be a no-op. React template has no docker-compose; not a defect per se but `just up` builds+runs a single container, inconsistent with the other stacks.

## 5. CLI surface

`pyproject.toml [project.scripts] soup = "orchestrator.cli:app"` → matches the Typer `app = typer.Typer(...)` in `orchestrator/cli.py` line 33. OK.

**Justfile recipes vs CLI commands:**

| Justfile | Routes to | Exists in CLI? |
|---|---|---|
| `just plan` | `orchestrator.cli plan "{{goal}}" --dry-run` | `plan` exists but has no `--dry-run` flag — Typer rejects unknown option |
| `just go` | `orchestrator.cli go "{{goal}}"` | missing |
| `just go-i` | `orchestrator.cli go "{{goal}}" --interactive` | missing |
| `just quick` | `orchestrator.cli quick "{{ask}}"` | missing |
| `just install` | `orchestrator.cli install {{mode}}` | missing |
| `just verify` | `orchestrator.cli verify --ref HEAD` | `verify` exists, no `--ref` flag, only prints stub |
| `just verify-run` | `orchestrator.cli verify --run …` | `--run` flag not defined |
| `just new` | `orchestrator.cli new …` | missing |
| `just worktree` / `worktree-rm` | `orchestrator.cli worktree …` | missing |
| `just logs` / `experiments` / `last-qa` | `orchestrator.cli logs --tail` etc. | missing |
| `just clean` / `doctor` | `orchestrator.cli clean/doctor` | missing |

Net: **justfile names 10+ Typer subcommands that do not exist**. The only commands that actually function are `soup plan <goal>` (no flags match justfile), `soup run <path>`, `soup status`, and the stubbed `verify/ingest/search`.

## 6. RAG wiring

- `lightrag-hku>=1.0` in `pyproject.toml` deps — OK.
- `rag/mcp_server.py` implements FastMCP server with `rag_search`, `rag_ingest`, `rag_list_sources` tools — complete.
- Sources implemented for github, ado-wiki, filesystem, web-docs — all four in `rag/sources/`. Each emits `Chunk` objects via `iter_chunks()`.
- **Stubs marked but not implemented:** `LightRagClient._build_lightrag()` relies on LightRAG's `PGKVStorage`/`PGVectorStorage` but makes no attempt to verify the Postgres schema is created; also uses `hybrid → "mix"` mapping that assumes modern LightRAG.
- **Real gap:** the module-level CLI entry points that every other component depends on (search.py and ingest.py "as scripts") do not exist. This is the single largest contract break in the repo.

## 7. Hooks logic

All 6 hooks present and referenced. Event-name consistency: ✓. Permissions: `settings.json` allows `Bash(python:*)`, `python3:*`, `py:*` — each hook invokes `python .claude/hooks/<name>.py` which is fine. However:

- Hooks write to `logging/agent-runs/session-{sessionId}.jsonl` via `SOUP_LOG_DIR` env — env is set in `settings.json` `"env"` block as `${workspaceFolder}/logging/agent-runs`. `${workspaceFolder}` is a VS-Code interpolation token; Claude Code's hook runner may or may not resolve it, and the Python hooks fall back to `os.environ.get("SOUP_LOG_DIR") or (root / "logging" / "agent-runs")`. On Claude Code CLI this will likely leak as a literal string; the fallback saves it. Low-severity but worth flagging.
- `pre_tool_use.py` `_matches_any` uses `fnmatch` without `pathlib.PurePath.match`; glob `src/**/*.py` will NOT match subdirectories (fnmatch is shallow). Scope enforcement is weaker than `files_allowed` suggests.
- Constitution VI.3 requires a pre-commit hook scanning for high-entropy strings and key prefixes — no such hook file. Secrets scanning is only in `security-scanner` agent text (plans only to invoke `gitleaks`); there is no installed pre-commit machinery.

## 8. Dead references

- `.claude/agents/utility/researcher.md` — not referenced, not in library.yaml.
- `.claude/hooks/setup.init.log` — referenced by `.claude/commands/install.md` step 2; no code writes it.
- `docs/codebase-map.md` — promised by `/map-codebase`; not present (it is generated on demand — not a defect).
- `.soup/rag-sources.json` — promised by `/rag-ingest` workflow; no code writes it.
- `docs/PATTERNS.md` references `rag/ingest.py` as accepting new URI schemes — consistent with the Python `Ingester.build_source` method but not with the missing CLI argparse.
- No broken relative markdown links detected in the sampled docs; DESIGN, README, CONSTITUTION link only to filenames present on disk.

---

## Top 10 hard gaps (blocking production readiness)

| # | Gap | Evidence | Fix |
|---|-----|----------|-----|
| 1 | `rag/search.py` and `rag/ingest.py` lack `__main__`/argparse; every agent, skill, command, hook, justfile recipe that shells out to them fails. | `Grep __main__` in `rag/` returns only `mcp_server.py`. `subagent_start.py:78` runs `sys.executable script query`. `rag-researcher.md:19` calls `python rag/search.py --query <q>`. | Add `argparse`-backed `main()` to both modules; or change all call sites to `python -m orchestrator.cli search "<q>"` after fixing gap #3. |
| 2 | Justfile routes 10+ subcommands to `orchestrator.cli` that do not exist (`go`, `go-i`, `quick`, `install`, `new`, `worktree`, `worktree-rm`, `logs`, `doctor`, `clean`). | `justfile` lines 56, 70, 76, 82, 144, 148, 152, 158, 162, 184, 192; `orchestrator/cli.py` defines only `plan, run, status, verify, ingest, search`. | Implement the missing Typer commands, or rewrite justfile to use the existing commands (`plan`, `run`, inline bash for the rest). |
| 3 | `soup ingest` / `soup search` call module-level `rag.ingest(...)` / `rag.search(...)` that are not exposed. | `orchestrator/cli.py:167-180`; `rag/__init__.py` exports only classes. | Add thin async-run wrappers in `rag/__init__.py` (e.g. `def ingest(uri): …; def search(q): …`) that construct `LightRagClient.from_env()` and call `Ingester`/`Searcher`. |
| 4 | `orchestrator.cli verify` is a print-stub, while Constitution IV makes the QA gate mandatory. | `orchestrator/cli.py:144-157` prints "qa-orchestrator wiring pending". `justfile verify:` routes here. | Spawn `qa-orchestrator` subagent via `agent_factory.spawn` with a hand-rolled `TaskStep`, parse emitted JSON as `QAReport`, exit non-zero on BLOCK. |
| 5 | `test-runner` agent referenced in DESIGN §4 and `/verify.md` but does not exist; `verifier` is aliased in qa-orchestrator.md only. | `schemas/execution_plan.py::ExecutionPlanValidator` would reject `test-runner` in a plan. Grep returns only agent-text references, no file. | Either add `.claude/agents/test-runner.md` + library.yaml entry, or delete every `test-runner` mention and unify on `verifier`. |
| 6 | `settings.json` PreToolUse matcher includes `MultiEdit`, but no agent's `tools:` frontmatter includes `MultiEdit`. | `.claude/settings.json:173`; grep `^tools:` in `.claude/agents/` shows only `Read, Edit, Write, …`. | Add `MultiEdit` to dev-focused agents' `tools:` lists, or remove `MultiEdit` from the matcher. |
| 7 | `AskUserQuestion` used by `/clarify`, `/constitution`, `/install` — not allow-listed or declared anywhere. | `clarify.md:18`, `constitution.md:18,20,33`, `install.md:18,24`; no agent frontmatter includes it; `settings.json` `permissions.allow` has no entry. | Add `AskUserQuestion` to the permitted tool list and to the frontmatter of any agent invoking it (orchestrator, spec-writer candidates). |
| 8 | `rag_queries` per-step plumbing does not reach subagent. `agent_factory.spawn` passes `--rag-queries` JSON to CLI but `subagent_start.py` reads only `SOUP_RAG_QUERIES` env var. | `agent_factory.py:98`; `subagent_start.py:115`. | Either set `SOUP_RAG_QUERIES` in `full_env` before spawn, or switch hook to read from a per-session sidecar file. |
| 9 | Two skills promised by DESIGN §5 — `using-git-worktrees`, `requesting-code-review` — have SKILL.md on disk but are NOT in `library.yaml`. | `library.yaml` catalog entries vs `.claude/skills/` listing; DESIGN.md §5 "Coordination (flexible)" names both. | Add both skills to `library.yaml` with `type: skill`, correct upstream, correct requires. |
| 10 | Dotnet template ships empty `Migrations/` (README only). EF Core expects at least one migration for the template to be "runnable" end-to-end as DESIGN §2 pillar 11 claims. | `templates/dotnet-webapi-postgres/Migrations/` contains only `README.md`. | Generate `0001_Initial.cs` via `dotnet ef migrations add Initial` inside the template and commit; or add a justfile recipe that runs it on first-boot. |

Word count: ~1,870.
