# Final Audit — Architecture & Internal Coherence

_Reviewer: independent software architect. Scope: `C:\Users\ethan\AIEngineering\soup\` as of 2026-04-14. Question: is the framework internally consistent, well-factored, and extensible?_

## 1. Verdict

**APPROVE_WITH_CAVEATS.**

Soup is a well-factored, coherent framework. The 16 pillars each have concrete code; the spec → plan → ExecutionPlan → waves → subagents → QAReport pipeline is traceable and serialized through Pydantic; the schemas are strict; the hooks do real work. Post–cycle-1 fixes have closed the biggest gaps from the completeness review (CLIs on `rag/search.py` and `rag/ingest.py`; missing Typer subcommands; cost estimation; env hardening in the agent factory). What remains is not structural — it is a handful of seams where naming drifts between DESIGN.md and code, where the Claude Code CLI invocation contract is implicit, and where extension friction is uneven across the four extension axes. These are fixable without re-architecting.

## 2. Pillar coverage matrix

| # | Pillar | Owner (module/file) | Concrete artifact | Coherence |
|---|---|---|---|---|
| 1 | Skills | `.claude/skills/<name>/SKILL.md` | 14 SKILL.md files, YAML frontmatter + iron laws | Clear |
| 2 | Agent roster | `.claude/agents/*.md` + `REGISTRY.md` | 22 agent files; tier/model/tool budget in frontmatter | Clear |
| 3 | Commands | `.claude/commands/*.md` | 14 commands; `/implement` composes cleanly with orchestrator.md | Clear |
| 4 | Hooks | `.claude/hooks/*.py` + `settings.json` | 6 hooks, all wired in `settings.json`; JSONL events | Clear, but hook↔orchestrator contract implicit (see §4) |
| 5 | Rules | `rules/{global,python,dotnet,react,typescript,postgres}/*.md` | Stack subtrees injected by `pre_tool_use.py` | Clear |
| 6 | Schemas | `schemas/*.py` | Pydantic v2, `extra="forbid"`; roster check in `TaskStep` | Clear, strong |
| 7 | Orchestrator | `orchestrator/orchestrator.py` | Wave loop, verify, commit, fix-cycle, state, experiments TSV | Clear |
| 8 | Meta-prompter | `orchestrator/meta_prompter.py` | opus call + 3-retry self-correct + ephemeral caching | Clear |
| 9 | RAG | `rag/{client,ingest,search,mcp_server,sources/*}.py` | LightRAG facade, 4 source adapters, MCP + CLIs | Clear after cycle-1 fixes |
| 10 | CLI wrappers | `cli_wrappers/{ado,docker,dotnet,gh,git,psql}.py` | Six typed wrappers | Clear |
| 11 | Templates | `templates/{python-fastapi-postgres,dotnet-webapi-postgres,react-ts-vite,fullstack-python-react}/` | Each has CLAUDE.md + justfile + Dockerfile (dotnet migrations still a thin placeholder per cycle-2 dotnet review) | Caveat |
| 12 | Justfile | `justfile` + `orchestrator/cli.py` | Typer app; 15+ subcommands implemented | Clear |
| 13 | Logging | `logging/agent-runs/*.jsonl`, `logging/experiments.tsv` | `post_tool_use.py`, orchestrator `_append_experiment` | Clear |
| 14 | Library catalog | `library.yaml` | 14 skills + 22 agents; roster source of truth | Clear |
| 15 | Worktrees | `.soup/worktrees/` + `soup worktree` CLI | CLI helper present; orchestrator commit path worktree-aware | Clear |
| 16 | Memory | `CLAUDE.md`, `MEMORY.md`, `.soup/memory/` | Tier table in ARCHITECTURE.md §6 matches disk | Clear; dream-consolidation still deferred (DESIGN §10) |

All 16 pillars have clear ownership and at least one concrete artifact. The single pillar with an outstanding caveat is Templates (dotnet migrations remain a stub).

## 3. Where the abstractions are clean

1. **ExecutionPlan as the hard contract.** `schemas/execution_plan.py` is the crispest file in the repo: `TaskStep` is `extra="forbid"`, the agent name is validated against a module-level roster loaded from `library.yaml`, `ExecutionPlanValidator` enforces DAG-level invariants (no cycles, all depends_on resolve, roster membership), and `compute_waves` in `orchestrator/waves.py` is a pure function of the step list. This means any producer (meta-prompter, a future template, a human with a text editor) can emit a plan, and the orchestrator will execute it byte-for-byte identically.
2. **Separation between agentic planning and deterministic execution.** Tenet 4 ("deterministic where possible, agentic where necessary") is actually honored in code. The meta-prompter is the *only* LLM call in the planning loop; once the plan is validated, the orchestrator has no LLM dependency for sequencing — it runs subprocesses, waits, reads exit codes, commits. This is a real architectural decision, not a slogan.
3. **QAReport verdict derivation.** `QAReport.verdict_from_findings` is a deterministic function of `findings` and `test_results`, not an LLM judgement. The blocking rules (§3 of DESIGN, Article IV of CONSTITUTION) are encoded as constants at the top of `schemas/qa_report.py`. An auditor can re-derive any verdict from the raw findings.
4. **State is file-based and inspectable.** `orchestrator/state.py::RunState` writes JSON atomically (tmp + rename), persists after every step, and is reloadable. The `logging/experiments.tsv` append-only table is a parallel, low-cardinality record. Crashes leave a forensic trail; there is no hidden runtime DB.
5. **Agent factory enforces env hardening.** `orchestrator/agent_factory.py::_filter_parent_env` starts from an explicit whitelist rather than forwarding the parent environment. Credential-bearing keys flow in only when `TaskStep.env` names them and only if they appear in `_STEP_INJECTABLE_ENV_KEYS`. This is the pattern I would write from scratch.
6. **Three memory surfaces are disambiguated.** `CLAUDE.md` (session), `MEMORY.md` (long-term), `.soup/memory/*.md` (dream-consolidated), `logging/agent-runs/*.jsonl` (trace). The tier table in ARCHITECTURE.md §6 makes the Venn diagram non-overlapping.

## 4. Where the seams leak

1. **Claude Code CLI invocation contract is implicit.** `orchestrator/agent_factory.py::_build_invocation` shells out to `claude -p <brief> --agent <role> --model <tier> --max-turns N --session-id <id> --files-allowed <csv> --rag-queries <json>`. These flag shapes are only validated by running the binary. There is no `docs/CLI-CONTRACT.md` pinning which flags `claude` is expected to accept, and `--rag-queries` in particular is passed as a flag but then read out of an env var (`SOUP_RAG_QUERIES`) by `.claude/hooks/subagent_start.py`. Two pieces of code meet at an undocumented wire.
2. **Hook ↔ orchestrator boundary is not a named protocol.** `agent_factory._forward_stderr_events` parses stderr for JSON lines and validates them as `AgentLogEntry`. That implies hooks emit `AgentLogEntry` JSON to stderr. The schema is documented in `schemas/agent_log.py`, but nothing in the hooks says "this is what I emit." A new hook author has to reverse-engineer the pattern by reading `post_tool_use.py`.
3. **`test-runner` ghosts.** DESIGN §4 and §3 still talk about "code-reviewer + security-scanner + test-runner in parallel" in prose. `verifier` is the real agent (REGISTRY absorbs `test-runner` into it). If someone reads DESIGN and writes a plan with `agent: "test-runner"`, `ExecutionPlanValidator` rejects it. The cycle-1 review flagged this; DESIGN.md §2 row 4 and the §4 flow still need to be reworded.
4. **`soup-init` vs `soup new` are parallel names.** `.claude/commands/soup-init.md` is the slash-command; `soup new <template> <name>` is the CLI subcommand; `just new` in the justfile routes to `soup new`. The three names for the same operation (scaffold a template) force a new reader to infer the mapping.
5. **Orchestrator commits everything with `git add -A`.** `orchestrator.py::_atomic_commit` stages the entire tree (`git add -A`) even though each step declares `files_allowed`. If a subagent accidentally drops a non-allowed artifact (cache, log, `.tmp` file) in the worktree, it gets committed. The `files_allowed` contract is enforced by the pre-tool-use hook at edit time, not at commit time — so a tool that bypasses Edit/Write (e.g. a Bash-produced file) slips through.
6. **Meta-prompter roster load has a cold-path.** `schemas/execution_plan.py::_try_load_default_roster` is best-effort at import; a missing or malformed `library.yaml` silently results in `_ACTIVE_ROSTER = set()`, which makes the `TaskStep.agent` field-level validator skip its check and defer to `ExecutionPlanValidator`. If a caller uses `TaskStep(...)` directly (or `model_validate` without context), they get a nominally-valid TaskStep whose agent may not exist. This is an acceptable trade-off for test ergonomics, but the fallback is silent.
7. **Cost estimate is a different world than Anthropic's invoice.** `orchestrator.py::_estimate_cost_usd` hardcodes per-tier rates. `experiments.tsv` marks them with a `~` prefix, which is honest, but there is no version stamp on the pricing table. When Anthropic changes prices, historical rows become incomparable without a pricing-version column.

## 5. Extensibility scorecard

| Scenario | Grade | Rationale |
|---|---|---|
| **New language (Go)** | Easy | Add `rules/go/*.md`; extend `.claude/hooks/pre_tool_use.py` extension routing; add stack hint in `.claude/hooks/subagent_start.py::STACK_EXT_HINT`; add a `go-dev` agent file + `library.yaml` entry; optional `templates/go-fiber-postgres/`. No schema or orchestrator change. Four files edited, all well-localized. |
| **New model provider (non-Anthropic)** | Hard | `schemas/execution_plan.py::ModelTier` is `Literal["haiku","sonnet","opus"]` and `agent_factory._build_invocation` hardcodes `--model <tier>` passed to the `claude` binary. The CLI subprocess is *the* Claude Code CLI; there is no abstraction layer. Swapping providers would require either (a) wrapping every non-Claude model as an MCP server that the Claude binary can call, or (b) fork the factory to emit OpenAI/Ollama CLI invocations. `orchestrator.py::_MODEL_PRICING_USD_PER_MTOKEN` likewise hardcodes Anthropic tiers. No ProviderAdapter seam exists. |
| **New RAG backend (not LightRAG)** | Medium | The dataclass `rag/client.py::LightRagClient` has the right external shape (async `ingest`/`search`/`close`), and `Retrieval`/`IngestReport`/`Chunk` are neutral models. But `LightRagClient` is a concrete class everywhere — `Ingester`, `Searcher`, the MCP server all import it by name. There is no `RagClient` `Protocol` that `LightRagClient` implements. The cleanest refactor is: extract a `RagBackend` protocol (with `ingest`/`search`/`list_sources`), rename the class to `LightRagBackend`, and have `from_env()` dispatch to the configured backend. A single day's work, but currently a cross-cutting edit rather than a drop-in replacement. |
| **New review agent (e.g. `accessibility-scanner`)** | Easy | Write `.claude/agents/accessibility-scanner.md`, register in `library.yaml`, extend `.claude/agents/qa-orchestrator.md` to dispatch it alongside the existing reviewers, and let it emit `Finding` rows with the existing severity/category enums. If the category doesn't fit the `Literal["security","correctness","style","test","coverage"]` enum, widen `schemas/qa_report.py::Category` — but that is a principled single-file edit. |

The extensibility story is strong on the language and review-agent axes, medium on RAG backends, and weak on model providers. The model-provider coupling is the one place where the framework made an opinionated bet ("we run the Claude Code CLI") without leaving an escape hatch.

## 6. Critical consistency violations

None that block. Minor:

- **Naming drift: `test-runner` in DESIGN prose vs `verifier` in code** (cycle-1 completeness review §2.4). DESIGN.md should be updated in one pass; the code is already self-consistent.
- **`utility/researcher.md` is in `library.yaml` but not in `REGISTRY.md` roster tables** — REGISTRY mentions it under Utility; library.yaml registers it — so this is resolved. I initially flagged it; checked both, it's fine.
- **`files_allowed` is enforced at edit time but not at commit time.** `_atomic_commit` uses `git add -A`. If a Bash tool call writes a file outside the glob, it gets committed. This is a real gap, but it is bounded by the permission list and the sandbox; severity medium.
- **MCP server (`rag/mcp_server.py`) never calls `client.close()`.** The FastMCP `mcp.run()` blocks; the client's `LightRAG` instance is built lazily on first tool call and then held for the process lifetime. Fine for a long-running MCP, but the `close()` method exists, suggesting lifecycle was imagined and then not wired.

No blocking contract breaks. Every critical seam the cycle-1 reviewer flagged has been closed in the current code.

## 7. Top 3 architectural improvements, ranked

1. **Introduce a `RagBackend` protocol and a `ProviderAdapter` protocol (or at least a ModelId value object).** Today, `LightRagClient` and the Claude Code CLI are hardcoded as *the* implementations. Extracting two small protocols — one for RAG (ingest/search/list_sources) and one for model invocation (spawn-a-subagent-with-role) — would turn both hard-edge extensions (new RAG, new model provider) into drop-ins. Neither protocol is speculative: they are implied by what the code already does and would take a few days each. This is the single change that would move the extensibility score for "new model provider" from Hard to Medium.
2. **Publish `docs/CLI-CONTRACT.md` pinning the `claude -p` flag shape that `agent_factory._build_invocation` assumes.** The framework runs real money through that invocation — it is the one place where schema, hook, orchestrator, and external binary all meet. Right now the contract is implicit: the flags that get passed (`--agent`, `--model`, `--max-turns`, `--session-id`, `--files-allowed`, `--rag-queries`) are only validated by running the binary. A single markdown page enumerating the exact Claude Code CLI flags we depend on, with a version guard (fail fast if the binary's `--version` differs from a known-compatible range), would protect against silent drift when Claude Code ships a new CLI. This also lets non-Anthropic ProviderAdapters (item 1) be written against a known shape.
3. **Close the `files_allowed` loop at commit time, not just edit time.** `orchestrator.py::_atomic_commit` currently `git add -A`s. Have it compute the allowed-glob set for the step, union it, and `git add <each-matching-path>`, then check that the staged diff is a subset of the allowed set. If a Bash-produced file lands outside, fail the commit rather than silently including it. This makes the constitutional guarantee ("`files_allowed` is enforced") true end-to-end rather than only at the Edit/Write boundary.

Also worth mentioning but below the top three: widening `schemas/qa_report.py::Category` to include `accessibility`, `performance`, `docs` so review-agent pillar growth doesn't require enum hacks; versioning the pricing table in `orchestrator/pricing.py` with a dated tuple so historical `cost_usd` rows can be reinterpreted; and writing `docs/CONTRACT.md` describing the hook↔orchestrator JSONL-over-stderr protocol so new hooks don't have to reverse-engineer it.

---

_Audit limits: I did not exercise the runtime — no `just go "<goal>"`, no `claude -p` spawn. Every finding is based on code reading plus the cycle-1 completeness review cross-check. The framework would benefit from an end-to-end smoke test (one tiny spec → plan → run → verify) captured as a CI job. That is the thing I cannot audit from files alone._

Word count: ~1,720.
