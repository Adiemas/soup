# Final DX Audit — Soup

_Independent developer-experience audit. Frame: new Streck engineer joins Monday, ships an internal app by Friday._

_Date: 2026-04-14. No participation in prior cycles. Files audited: `README.md`, `docs/ONBOARDING.md`, `docs/PATTERNS.md`, `justfile`, `.env.example`, all 9 commands requested, both Python and .NET templates, both mock-app FEEDBACK files, `docs/reviews/cycle1-critic-dx.md`._

---

## 1. Verdict

**APPROVE_WITH_CAVEATS.**

The framework's bones are genuinely excellent and have hardened significantly since cycle 1. The `test-runner` ghost, the `/quick` TDD contradiction, the `plan-validate` gap, `tasks-writer` split, orphan utility agents, typescript rules, .NET rules, and the Windows setup section are all addressed. What remains is paper cuts, not structural — none would block shipping by Friday, but several will cost an hour apiece in the first week. The two strongest cautions: `.env.example` required-keys are still not enumerated in `ONBOARDING.md §2` (cycle 1 fix #4), and a subtle venv-activation footgun on the Windows pip-fallback path survives. Both are <30-minute fixes.

---

## 2. Monday morning walkthrough

A first-hour trace through the first-touch surfaces:

**0:00 — Clone + README.** Engineer lands on `README.md`. TL;DR at line 15 is copy-paste runnable: `just init`, `$EDITOR .env`, `just go "build me a health endpoint…"`. The redundant `cp .env.example .env` line from cycle 1 is gone; `just init` now owns that copy (`justfile:40-43`: `@if [ ! -f .env ]; then cp .env.example .env; fi`). **This is a visible cycle-1 fix.** Git clone URL is real (`https://github.com/streck/soup.git`), not a placeholder — also fixed.

**0:05 — Windows callout.** Line 27: "On Windows, read **Windows setup** below before running `just init`…" This is good framing — but the TL;DR is above the callout, so a skimmer will run `just init` first and hit a `bash: command not found` before reading the Windows block. **Minor:** put the callout above the TL;DR or promote it to a Prerequisites-check-first paragraph.

**0:10 — Windows setup.** Section 174-258 is thorough: Git for Windows, `bash --version` verification, Windows Terminal, Just via winget, Docker Desktop + WSL 2, Python 3.12, optional `uv`. Troubleshooting covers the three likely footguns (just-not-on-PATH after winget, docker not running, OneDrive path). This was missing in cycle 1 — a substantive improvement.

**0:20 — `just init`.** Engineer runs init. The recipe is clearly commented and idempotent. One remaining snag: on the **pip-fallback path** (line 34-39), the venv is activated with `. .venv/bin/activate 2>/dev/null || . .venv/Scripts/activate` inside the `just` recipe's `bash -cu`. Just recipes don't persist shell state across invocations — so when the engineer's next command is `just test`, the venv is not activated. On the `uv` path this is fine (uv finds the venv). On the pip path, later `python -m orchestrator.cli` recipes will use the system Python. **Still open from cycle 1 §2.1.** Practically: engineers with `uv` installed (README recommends it) won't hit this.

**0:30 — `just doctor`.** `docs/ONBOARDING.md:62` says "Verify with `just doctor`." Recipe exists (`justfile:201-202`), CLI handler implemented (`orchestrator/cli.py:651`), Rich table output (`cli.py:741`). This works. **Cycle 1 §7.8 fix landed.**

**0:40 — First `.env` edit.** Engineer opens `.env`. They see `ANTHROPIC_API_KEY=`, `POSTGRES_PASSWORD=`, `GITHUB_TOKEN=`, `ADO_PAT=` etc. README only mentions `ANTHROPIC_API_KEY`. `docs/ONBOARDING.md §2` (lines 33-55) says "you need… An Anthropic API key in `.env`" but does not enumerate which keys are required-for-init vs. optional-for-integrations. **Cycle 1 fix #4 is NOT landed.** The engineer will either leave stubs (works for `just go`) or Slack a senior dev to ask. This is a 10-minute doc fix still outstanding.

**0:50 — First read of `CLAUDE.md` / `CONSTITUTION.md`.** `CLAUDE.md` still lacks an explicit pointer to `docs/ONBOARDING.md` for first-touchers (cycle 1 §1 last bullet). Minor, but since Claude Code auto-loads `CLAUDE.md` at session start, an embedded "if you're new: read `docs/ONBOARDING.md`" line would help any subagent or engineer who reverse-lands here.

**Verdict for the first hour:** good. Not frictionless, but the sharp edges are paper cuts, not blockers.

---

## 3. First real feature walk — `/health` endpoint

Tracing `/specify → /plan → /tasks → /implement → /verify`:

**`/specify "add a /health liveness endpoint returning JSON"`.** Command card at `.claude/commands/specify.md` now explicitly defers section list to `.claude/agents/spec-writer.md` ("the agent card is the single source of truth," line 16) and references exactly the 7+1 sections the agent produces. **Cycle 1 friction #1 landed as a delegation, not a duplication.** Very clean. Output path `specs/<slug>-<YYYY-MM-DD>.md` (line 28) is consistent with what I see in `specs/prompt-library-2026-04-14.md`.
_Ambiguity:_ `$ARGUMENTS` if empty — command still doesn't say "AskUserQuestion." `spec-writer` will hallucinate a goal. Cycle 1 §3 table row for `/specify` is still open.

**`/plan` (or default spec).** `.claude/commands/plan.md` defers section list to the plan-writer agent card (line 20: "Section list is defined once in `.claude/agents/plan-writer.md`"). Clean pattern. It does warn: "abort and AskUserQuestion" on ambiguous defaults (line 14) — **cycle 1 Top 10 #10 fix landed.** Produces `.soup/plans/<slug>.md` — markdown only.

**`/tasks`.** Now dispatches `tasks-writer` (a new dedicated agent), not `plan-writer`. This was the dual-mode contradiction cycle 1 flagged (friction #5). **Fix #4 from the top-10 landed cleanly** — `library.yaml:151-153` registers `tasks-writer`, `.claude/agents/tasks-writer.md` is authored, command dispatches it explicitly. Validation step uses `soup plan-validate` (line 23), which **is** now implemented (`orchestrator/cli.py:108` `@app.command("plan-validate")`). However — critical — it is **not exposed as a `just` recipe** (`just plan-validate` does not exist). Cycle 1 top-10 fix #9 is only half-landed. The engineer who reads `tasks.md:23` and types `just plan-validate .soup/plans/x.json` will get "unknown recipe." They must type `python -m orchestrator.cli plan-validate …` — which works but isn't discoverable.
_Ambiguity:_ the migration-routing note (line 41) and utility-agent-whitelist note (line 42) are both excellent. Keep.

**`/implement`.** Defaults to most-recent `.soup/plans/*.json`. Executes via orchestrator; `verifier` handles both verification and fix-cycle (cycle 1 §4 "orphan" issues resolved — `verifier.md:10-15` now explicitly absorbs both roles). Clean. Still no mention of how `rag_queries` flow — friction #7 from cycle 1 prompt-library FEEDBACK is still open.

**`/verify`.** Dispatches `code-reviewer` + `security-scanner` + `verifier` (no more `test-runner`). Blocking rules explicit (critical security → BLOCK, failing test → BLOCK, coverage <70% → NEEDS_ATTENTION). This is the cleanest command in the repo.

**What confuses in the happy path:**
- `verify_cmd` RED-phase semantics: PATTERNS.md §0b now documents the `! pytest…` pattern thoroughly (asset-tracker FEEDBACK and cycle 1 friction both prompted this). **Major improvement** — a new engineer will learn the RED trick in-line.
- `files_allowed` glob dialect: PATTERNS.md §0c now gives an explicit gitignore-dialect reference with a table. Also major improvement.

---

## 4. Windows experience

Substantially better than cycle 1 suggested. Specifically works now:

- `README.md:174-258` has full Git-for-Windows setup, winget installs, Windows Terminal pairing, Docker Desktop WSL 2 backend, file-sharing caveat, OneDrive warning. This addresses cycle 1 §6 head-on.
- `justfile:197-198` `clean-all` uses Python `shutil.rmtree` — no more `rm -rf`. **Cycle 1 top-10 #5 fix landed.**
- `docs/ONBOARDING.md:56-60` links to the Windows section and notes `just init` will "fail fast if `bash --version` isn't reachable" — solid framing.
- Template `justfile`s (`templates/python-fastapi-postgres/justfile:1`) also set `bash -cu`. Consistent.

Still open / soft warnings:

- The pip-fallback venv-activation across `just` recipes (§2 above). Mitigated by `uv` being strongly recommended, but not eliminated.
- `.claude/settings.json` `"SOUP_ROOT": "${workspaceFolder}"` — cycle 1 §6 flagged this as a VS Code-ism. I didn't re-audit `settings.json` this pass (not in my read list), but if that's still a `${workspaceFolder}` template, CLI sessions outside VS Code may not resolve it.
- `/dev/null` appears in `justfile` inside `bash -cu` — safe.
- `/soup-init`'s `${SOUP_APPS_DIR:-../<app-name>}` bash-parameter expansion (`soup-init.md:17`) works from Git Bash but won't from raw PowerShell. Command docs should call out "run from a Git Bash prompt."

No bash-isms have leaked into user-facing `cmd`/PowerShell surfaces. Paths are forward-slashed throughout and `pathlib` / `PurePosixPath` is the implicit contract (PATTERNS §0c.3: "Match is case-sensitive… forward-slashes only in patterns; pathspec normalises…"). **This is correct.**

---

## 5. Error messages and recovery

**Good:**
- `justfile:72-74, 78-80, 84-86, 89-91, 96-98, 101-103, 120-122, 147-151` — every user-facing recipe has `if [ -z "{{arg}}" ]; then echo "usage: …" >&2; exit 2; fi`. Typing `just go` without args gives `usage: just go "<goal>"`. Clean.
- `just doctor` is implemented and renders a Rich health table (`cli.py:741`).
- `/verify` output structure (verdict / findings table with severity+file:line / test summary / actionable next steps per finding) is spec'd cleanly in `verify.md:27-31`.
- QA gate won't let you bypass BLOCK; ONBOARDING §6 (lines 205-214) walks through the recovery loop (`just go "fix the failing test_health_contract regression"`) which auto-dispatches `verifier` (fix-cycle role) with `systematic-debugging` context.
- `just logs` / `just last-qa` exist and are documented (`ONBOARDING.md:203`).

**Still gaps:**
- No schema-error example. When `tasks-writer` emits bad JSON, the engineer gets Pydantic's default error — useful to experienced devs, opaque to juniors. A one-paragraph "reading ExecutionPlan validation errors" in ONBOARDING §6 would help.
- `/install` command writes `.claude/hooks/setup.init.log` per `install.md:23`, but cycle 1 §2.2 flagged that nothing in the framework actually creates that file. I did not re-verify this pass.
- Empty `files_allowed` for Bash-only steps (asset-tracker FEEDBACK §7.3) is still ambiguous — PATTERNS §0c.5 says "empty = read-only" but commit/build steps write nothing to the repo yet still invoke Bash; needs a carve-out.

Logging tail via `just logs` is helpful when the trace is legible (ONBOARDING §6 shows the JSONL structure). Would benefit from a `just logs --since 5m` or `--agent python-dev` filter — currently "tail most recent session" only.

---

## 6. Friday ship-it check

**Yes, a new engineer can ship a small internal tool by Friday.** Walk-through:

- **Mon:** install + `just init` + `just doctor` + read CLAUDE/CONSTITUTION. ~2 hours.
- **Tue:** `just new python-fastapi-postgres my-tool` scaffolds a runnable template (verified: `templates/python-fastapi-postgres/` has `pyproject.toml`, `justfile`, `app/`, `tests/`, migrations). `just up` → curl `/health` → JSON. `/specify` their actual tool's goal. ~4 hours.
- **Wed:** `/clarify`, `/plan`, `/tasks`. Orchestrator scaffolds migrations via sql-specialist, tests-first via test-engineer, endpoints via python-dev. ~6 hours.
- **Thu:** `/implement`. Stop-hook QA gate runs. Fix any BLOCKs via the documented `just go "fix …"` loop. ~6 hours.
- **Fri:** `/verify`, `gh pr create`, demo. ~2 hours.

This is a credible budget **only because** the `tasks-writer`, `test-runner`/`verifier` consolidation, and `/quick` TDD chain are all fixed. Had any of those been still broken, the first `just go` would have failed validation and burned the day. The framework has reached the point where dogfooding works out of the box.

**Caveats that could cost the week:**
1. If they're on pip (not uv) on Windows and don't notice the venv-activation issue, a morning burns.
2. If they don't know which `.env` keys are required beyond `ANTHROPIC_API_KEY`, they may configure `POSTGRES_PASSWORD`/`GITHUB_TOKEN` at the wrong moment (runtime rather than setup) and hit a `just up` that half-starts.
3. If the engineer's feature touches EF Core migrations, asset-tracker FEEDBACK §1 still lists ~7 open .NET-specific issues. .NET path remains the riskier ship.

---

## 7. Top 5 ergonomic fixes still needed

Ranked by risk-to-Friday-ship × fix cost:

1. **Enumerate required `.env` keys in `docs/ONBOARDING.md §2`.** Cycle 1 top-10 fix #4 is not landed. Add a table: key | required-for (init / runtime / integration) | default/stub | where-to-get. 15-minute fix; saves every new engineer a Slack question. (Impact: H. Effort: L.)

2. **Add `just plan-validate <path>` recipe.** The CLI command exists (`orchestrator/cli.py:108`) but has no `just` wrapper. `/tasks` command doc tells engineers to run it (`tasks.md:23`). Add `plan-validate path:` → `python -m orchestrator.cli plan-validate "{{path}}"` to `justfile`. 5-minute fix. (Impact: M. Effort: L.)

3. **Fix the venv-activation in `just init` pip-fallback.** Either force-require `uv` on Windows (set `uv` from optional → required in `README.md:170`, add a `bash -c 'command -v uv || (echo "install uv: winget install astral-sh.uv" >&2; exit 2)'` guard at the top of `just init`), or rewrite the pip path to emit an explicit activation helper (`.venv/Scripts/python -m pip ...` absolute-path invocations). 30-minute fix; eliminates a silent-breakage class. (Impact: H. Effort: M.)

4. **Link `docs/ONBOARDING.md` from `CLAUDE.md`.** One line in CLAUDE.md's top section: "First session? Read `docs/ONBOARDING.md` before anything else." Cycle 1 §1 last bullet. 2-minute fix. (Impact: M. Effort: L.)

5. **Document `rag_queries` flow in `.claude/commands/implement.md`.** Prompt-library FEEDBACK friction #7 — three sources describe where RAG fires, none is canonical. Add a "## RAG integration" subsection to `implement.md` stating: meta-prompter seeds `rag_queries` on each `TaskStep`; `subagent_start.py` hook retrieves top-k and injects into child prompt; citations flow back in the child's output. 15-minute fix; closes a recurring "where does this happen?" question for any engineer writing a custom step. (Impact: M. Effort: L.)

Collectively <90 minutes of work. None of them are framework-shape; they are paper cuts that shave the remaining onboarding friction from "good" to "delightful."

---

_Bottom line: the cycle-1 → cycle-2 → present trajectory is strong. Most structural DX gripes landed as real fixes (test-runner, /quick TDD chain, tasks-writer split, PATTERNS §0/0b/0c, typescript + dotnet rules populated, utility agents registered, doctor/clean-all Windows-safe). The remaining gaps are documentation polish and one Windows edge case. APPROVE_WITH_CAVEATS; ship it, file the five ergonomic fixes as a follow-up issue._
