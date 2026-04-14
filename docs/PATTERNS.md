# Patterns — Cookbook for Soup

Short, prescriptive recipes for extending the framework. Each recipe:
inputs → diff locations → test → done. Follow the file layout
exactly; hooks + `library.yaml` expect these paths.

See `DESIGN.md` for rationale, `ARCHITECTURE.md` for internals.

---

## 0. When to use a skill vs. command vs. hook vs. rule

Four extension surfaces, each with a distinct scope. Pick the one
whose enforcement model matches your problem — picking wrong means
either weak enforcement or duplicated logic across surfaces.

**Commands** are user-facing UX entry points — slash commands
(`.claude/commands/<name>.md`) and their `just` wrappers. Use a
command when you want an engineer to *choose* to invoke a capability,
and when the capability is a composition of agents + steps. Example:
`/verify` composes `verifier` + `code-reviewer` + `security-scanner`
into a single UX. **Agents** (`.claude/agents/<name>.md`) are the
roles those commands dispatch — use an agent when you need a named
specialist with a fixed tool allowlist and model tier, not a flow.

**Skills** (`.claude/skills/<name>/SKILL.md`) are *procedural gates* —
an iron law plus a numbered checklist that any agent can load before
acting. Use a skill when the rule is about **how you work on a task**
(TDD RED-before-GREEN, root-cause before fix, verify before claim).
Skills are agent-invoked and cross-cutting — they apply whether the
task is Python, .NET, or React. **Rules** (`rules/<stack>/*.md`) are
*static, file-scoped* — the `pre_tool_use` hook injects them at every
Edit/Write based on the file extension. Use a rule when the guidance
applies to *a kind of file* (no `eval()` in `.py`, strict tsconfig in
`.ts`, additive-only migrations in `.sql`).

**Hooks** (`.claude/hooks/*.py`) are automatic, non-bypassable
infrastructure. Use a hook when enforcement must be guaranteed — the
agent can't forget and the user can't skip. Injecting rules,
recording JSONL traces, dispatching QA on Stop, redacting secrets:
these are hooks because "the agent should remember" is not a real
enforcement model. If a skill or rule is worth having at all, its
irreducible-minimum enforcement lives in a hook.

**Decision table:**

| Need | Surface |
|---|---|
| User-facing UX for a flow | **Command** (+ `just` recipe) |
| Named role with tools + model | **Agent** |
| "When working on any task, do X first" | **Skill** |
| "When editing files of type Y, know Z" | **Rule** (`rules/<stack>/`) |
| "Every time tool A fires, enforce B" | **Hook** |

When in doubt: the more *automatic* and *non-negotiable*, the lower
down this list it lives. Commands are discretionary; hooks are
inevitable.

---

## 0b. TDD RED-phase `verify_cmd` — canonical pattern

In a TDD plan, the test-engineer's step writes a failing test. The
orchestrator runs the step's `verify_cmd`; if it exits 0, the step
is "verified." For a RED-phase step that means exit 0 MUST signal
"the test failed, as expected" — otherwise a successful test (which
should never happen yet) would be treated as a pass, and a failing
test would spuriously dispatch `verifier` (fix-cycle role).

**Canonical pattern:** prefix the command with `! ` (bash negation).
This inverts the exit code: a failing test (non-zero) becomes 0, a
passing test (zero) becomes 1 (which the orchestrator treats as a
legitimate failure — "your RED test accidentally passed").

```json
{
  "id": "S3",
  "agent": "test-engineer",
  "phase": "red",
  "verify_cmd": "! pytest tests/test_health.py::test_health_returns_200 -q"
}
```

Equivalent bash explicit form:

```bash
! pytest tests/test_health.py -q       # exit 0 = test failed (good)
```

Do **not** use `pytest ... || true` for RED-phase steps. That
swallows every possible signal: a passing test, a crashed runner,
and a missing test file all exit 0, masking real problems. The
`! `-prefix is strictly better because it distinguishes "exited
non-zero" (expected) from "exited zero" (unexpected success).

GREEN-phase steps use the plain command (exit 0 = test passed).

**Why this pattern beats a `verify_expects: "fail"` schema field:**
adding a new schema field requires updating `ExecutionPlan`,
`plan-writer`, the validator, and every consumer. The `! ` prefix
is a one-character bash idiom understood by every shell — no
schema changes required, and the intent is visible in the plan JSON.

---

## 0c. `files_allowed` glob dialect

`TaskStep.files_allowed` (`schemas/execution_plan.py`) accepts a list
of patterns interpreted as **gitignore-style globs**, matched via the
`pathspec` library (already pulled in transitively via `lightrag-hku`;
declare `pathspec>=0.12` directly in `pyproject.toml` under `dev`
when you add test fixtures that depend on it). Patterns are relative
to the repository root (not the worktree root) and are enforced by
the `pre_tool_use` hook on every Edit/Write.

**Supported syntax:**

| Pattern | Meaning |
|---|---|
| `src/app/main.py` | Exactly one file |
| `mock-apps/prompt-library/**/*.py` | All `.py` files recursively under that dir |
| `rules/*.md` | Markdown files at that level only (no recursion) |
| `tests/**` | Anything under `tests/` (files and subdirs) |
| `!mock-apps/prompt-library/tests/` | **Exclude** (leading `!` negates a prior allow) |

**Semantics:**

1. An Edit/Write is **allowed** iff at least one positive pattern
   matches *and* no negative (`!`-prefixed) pattern matches.
2. Multiple patterns are **OR**'d for positive matches. Negatives
   always win over positives — `!` is subtractive.
3. Match is case-sensitive on all platforms (pathspec default). On
   Windows, forward-slashes only in patterns; pathspec normalises
   the input path internally.
4. `**` matches zero-or-more path segments; `*` matches within a
   single segment; `?` matches a single character.
5. An empty list means "no writes allowed" — the step is read-only
   (use for verifier/reviewer-style steps).

**Example — a plan step that writes the test and nothing else:**

```json
{
  "id": "S3",
  "agent": "test-engineer",
  "files_allowed": [
    "mock-apps/prompt-library/backend/tests/**/*.py",
    "!mock-apps/prompt-library/backend/tests/fixtures/**"
  ]
}
```

This allows writing any `.py` under `backend/tests/` **except**
anything under `fixtures/`, which the step must not touch.

---

## 1. Add a new agent

**When:** you need a specialist the existing roster doesn't cover —
e.g. a `k8s-deployer` for internal services.

**Steps:**

1. Create the agent card at `.claude/agents/<name>.md`:

   ```markdown
   ---
   name: k8s-deployer
   description: Deploys internal services to the Streck k3s cluster via helm.
   model: sonnet
   tools: [Read, Bash, Write]
   ---
   You are the k8s-deployer. Your sole responsibility is rendering a
   helm chart and applying it. Never edit application code.
   ...
   ```

2. Register in `library.yaml`:

   ```yaml
   - name: k8s-deployer
     type: agent
     source: local:.claude/agents/k8s-deployer.md
   ```

3. Whitelist the agent name in `schemas/execution_plan.py::TaskStep.agent`
   Literal. (Without this, the meta-prompter cannot schedule it — the
   Pydantic validator rejects unknown agents. That's the point.)

4. Add a smoke test at `tests/agents/test_k8s_deployer.py` that
   dispatches the agent against a fixture helm chart and asserts the
   expected `helm diff` output.

5. Run `just test` — green? You're done.

**Gotcha:** agents must not span >10 turns (Constitution II.3). If the
task needs more, split into two agents with a `depends_on` edge.

---

## 2. Add a new skill

**When:** you have a procedural gate that should apply across tasks —
e.g. a `contract-first-api` skill that forces OpenAPI spec authorship
before code.

**Steps:**

1. Create `.claude/skills/<name>/SKILL.md` with superpowers-style
   frontmatter:

   ```markdown
   ---
   name: contract-first-api
   triggers:
     - "new endpoint"
     - "add route"
     - "REST API"
   requires: []
   ---
   # Iron law
   No endpoint code without an approved `openapi.yaml` excerpt for it.
   # Steps
   1. Write (or edit) openapi.yaml for the new route.
   2. Validate with `openapi-cli validate`.
   3. ONLY THEN write the route handler.
   # Enforcement
   pre_tool_use hook rejects Write of handler files whose path is not
   yet present in openapi.yaml.
   ```

2. Register in `library.yaml` (`type: skill`).

3. If the skill needs hook enforcement, extend
   `.claude/hooks/pre_tool_use.py` with the glob check — keep all rule
   logic in one place.

4. Document the trigger words in `rules/global/skills-index.md` so
   `user_prompt_submit` suggests it correctly.

5. Test: write a spec that should trigger the skill, run `just go`,
   confirm the subagent reaches for the skill in its transcript.

**Gotcha:** skill names are filesystem-safe (kebab-case). Don't use
spaces; hooks match by directory name.

---

## 3. Add a new command

**When:** you want a new slash-command UX — e.g. `/release` to cut a
tagged deploy.

**Steps:**

1. Create `.claude/commands/<name>.md`:

   ```markdown
   ---
   description: Tag + release the current branch
   argument-hint: [version]
   ---
   ## Workflow
   1. Validate branch is up to date with main.
   2. Run `just verify` — abort on non-APPROVE.
   3. Run `git tag v{{arg}}` and push.
   4. Create GitHub release via `gh release create`.
   ```

2. If the command has a shell shortcut, wire it into `justfile`:

   ```
   release version:
       @python -m orchestrator.cli release "{{version}}"
   ```

3. Commands inherit the full hook chain automatically.

4. Add to the command table in `README.md`.

---

## 4. Add a new rule (by stack)

**When:** a team policy needs to be enforced on every edit of a given
stack — e.g. "no `eval()` in Python".

**Steps:**

1. Drop a markdown file under `rules/<stack>/<name>.md`:

   ```markdown
   # No eval/exec in production code
   NEVER use `eval()`, `exec()`, or `compile()` on user input.
   Prefer ast.literal_eval for data parsing.
   Allowed exceptions: tooling in `scripts/` directory only.
   ```

2. The `pre_tool_use` hook picks up all files in `rules/<stack>/` at
   session start (no registration needed — glob-based).

3. Add a reviewer test in `tests/rules/test_python_eval.py` that asks
   `code-reviewer` to review a fixture containing `eval(x)` and
   asserts a critical finding emerges.

4. Rules are `rules/global/*.md` (always injected) +
   `rules/<ext>/*.md` (routed by file extension: py, cs, ts, tsx, sql).

---

## 5. Add a new RAG source adapter

**When:** you need to ingest a new content type — e.g. Confluence.

**Steps:**

1. Add a module at `rag/sources/<scheme>.py`:

   ```python
   # rag/sources/confluence.py
   from rag.sources.base import SourceAdapter, Document

   class ConfluenceAdapter(SourceAdapter):
       scheme = "confluence"
       def fetch(self, uri: str) -> list[Document]:
           # confluence://space/page — return normalized Document list
           ...
   ```

2. Register the adapter in `rag/sources/__init__.py`'s `ADAPTERS` dict.

3. `rag/ingest.py` will now accept
   `just rag-ingest confluence:STRECK/engineering-home`.

4. Test with a fixture page (use `responses` to mock HTTP).

5. Document the URI scheme in README's RAG section.

**Gotcha:** adapters MUST emit stable `Document.id`s (hash of
canonical URL + version). The graph depends on this for dedup.

---

## 6. Add a new template

**When:** a new internal app pattern emerges — e.g. `python-worker`
for background jobs, `nextjs-app-router` for App Router SaaS apps,
`ts-node-script` for scheduled TS jobs.

**The six touch-points.** Every new template must land these six
artifacts, or it will not survive first contact with a real repo:

1. **Copy the tree.** `templates/<slug>/` as a minimal-but-runnable
   scaffold — real `package.json` / `pyproject.toml`, real entry
   point, not a placeholder-only skeleton. An agent invoking
   `/soup-init <slug>` must be able to run `just dev` and `just test`
   on the first try.

2. **`CLAUDE.md`.** Stack-specific rules that extend the parent
   `CLAUDE.md` and `CONSTITUTION.md`. Declare the stack (framework,
   language, tests), the layout, the numbered rules agents must
   follow, and the "what NOT to do" section. Reference relevant
   `rules/<stack>/*.md` files.

3. **`README.md`.** Engineer-facing, not agent-facing. Quick-start
   commands, where to look for rules, a pointer to `CLAUDE.md`.

4. **`justfile`.** The canonical command surface: `init`, `dev`,
   `build`, `test`, `lint`, `typecheck`, plus any stack-specific verbs
   (`migrate`, `gen-types`, `scan`). `verifier` looks for `just test`
   first; if it isn't there, the template is invisible to the QA
   pipeline.

5. **Minimal runnable code + config.** At least one source file that
   exercises the stack's defining pattern — a Server Component for
   Next.js, an argv parser for a TS script, a FastAPI route for a
   Python service. No empty `src/main.ts` with a TODO.

6. **At least one passing test.** Unit test that proves the test
   runner is wired. For templates with e2e needs (Next.js, full-stack),
   ship a Playwright config plus one green e2e spec as well.

**And then register it:**

7. **Link from `.claude/commands/soup-init.md`.** Add the template
   slug to the `description:` line and the `$1` accepted list. Without
   this, users cannot discover the template via `/soup-init`.

**Gotchas:**

- Templates are scaffolding, not documentation. Heavy customization
  (theme choices, team-specific naming) belongs in the spawned repo,
  not the template. Keep the template lean.
- Library-catalog entries (`library.yaml`) are NOT required for
  templates — `/soup-init` globs `templates/` directly. Only add a
  catalog entry if the template is being served from a different
  repo (library pattern).
- If the template introduces new rules (e.g. `nextjs-app-router`
  needed `rules/supabase/`), write those rules in the same PR. The
  template's `CLAUDE.md` references them; a missing rules file means
  broken context injection at runtime.
- Name the directory after the STACK, not the project type.
  `templates/nextjs-app-router/` (clear) beats `templates/web-app/`
  (ambiguous).

**Example — `nextjs-app-router`:**

```
templates/nextjs-app-router/
  CLAUDE.md                     # touch-point 2
  README.md                     # touch-point 3
  justfile                      # touch-point 4
  package.json                  # touch-point 1
  tsconfig.json
  next.config.ts
  src/app/{layout,page}.tsx     # touch-point 5 (SC default)
  src/app/api/health/route.ts
  src/middleware.ts
  src/lib/supabase/{server,client}.ts
  e2e/health.spec.ts            # touch-point 6 (e2e)
  src/__tests__/smoke.test.ts   # touch-point 6 (unit)
  playwright.config.ts
  vitest.config.ts
  supabase/migrations/0001_init.sql
  Dockerfile
```

Then link from `soup-init.md`'s `description:` line and `$1` list.

---

## 7. Wrap a new CLI tool (CLI-Anything 7-phase)

**When:** agents need to call a tool that lacks a clean `--json`
interface — e.g. `kubectl`.

**Steps (CLI-Anything 7-phase, per `DESIGN.md §5`):**

1. **Survey** — man page, `--help`, common invocations. Save to
   `cli_wrappers/<tool>/_survey.md`.
2. **Contract** — write a Pydantic model for inputs and outputs.
3. **Wrap** — `cli_wrappers/<tool>/wrapper.py` — subprocess with
   `--output=json` (or parse text if no JSON). Always return the
   Pydantic model.
4. **Skill** — `.claude/skills/<tool>/SKILL.md` — prescribes WHEN and
   HOW to call the wrapper, with examples.
5. **Agent (optional)** — if the tool is invoked frequently enough to
   merit a dedicated agent, add `.claude/agents/<tool>-agent.md`.
6. **Test** — record a real invocation via VCR / `responses`, test
   the parser against the recording.
7. **Doc** — add a row to the CLI wrappers table in the README + an
   example in `cli_wrappers/<tool>/README.md`.

Existing references: `cli_wrappers/ado/`, `cli_wrappers/psql/`,
`cli_wrappers/docker/`, `cli_wrappers/dotnet/`, `cli_wrappers/git/`.

---

## 8. Run mock-app review loop

**When:** you've changed something in the framework itself and want to
confirm it doesn't regress real internal-app generation.

**Steps:**

1. Create a throwaway mock-app goal file, e.g.:

   ```bash
   cat > /tmp/mock-goal.txt <<'EOF'
   Build a python service that exposes /heartbeat returning {"ok": true}
   backed by postgres, with a migration and a pytest.
   EOF
   ```

2. Run the review loop via the framework:

   ```bash
   just go "$(cat /tmp/mock-goal.txt)"
   # once complete:
   just verify
   just logs > /tmp/mock-trace.log
   ```

3. Spawn the three-reviewer panel (inside Claude Code):

   ```
   /review --mock-app=/tmp/mock-* --reviewers=code,security,pm
   ```

4. Read each reviewer's report under
   `.soup/runs/<run-id>/reviews/`. Apply critical/high findings as a
   patch; re-run `just go` on the patched framework.

5. Cap: 5 iterations on the Python path, 3 on the C# path. If
   critical findings persist beyond that, the framework change needs a
   rethink — escalate via `/architect`.

**Why the cap?** Diminishing returns. Three-reviewer agreement is
reached fast; further loops pile on style-level nits that don't move
the verdict.

---

## 8b. Permission presets

**When:** you're onboarding a repo whose scope differs from soup's default
multi-stack allow-list — for example a pure TS script (no backend, no DB, no
Docker) or a code-gen repo that only needs `gh` + file tools.

**Problem:** `.claude/settings.json` lives in the soup repo and ships a
permissive allow-list covering Python, .NET, Node, Postgres, Docker, etc.
For a script-only repo that pattern is over-broad — the attack surface is
wider than the repo's actual tool needs, and the cycle-1 dogfood of
`claude-news-aggregator` (see `docs/real-world-dogfood/claude-news-aggregator.md`
§"Harmonization of `.claude/settings.local.json` narrow allow-lists")
surfaced that narrower presets are worth copying.

**Shape:** `.claude/settings.local.json` is per-clone / per-machine and
shadows `.claude/settings.json` keys. Soup ships named preset files in
`.claude/settings.presets/<name>.json` that you copy over
`settings.local.json` to adopt the narrower scope.

**Available presets:**

| Preset | When to use | Bash surface |
|---|---|---|
| `restricted` | Pure scripts, one-binary services, ops automation, cron jobs. Matches the `claude-news-aggregator` shape. | Only `gh auth:*`, `gh repo:*`, `git push:*`, `git status`, `git diff`, `git log`. Plus Read/Grep/Glob/Edit/Write. No language runtimes. |
| `development` | Default soup multi-stack feature work (Python + TS + .NET + Postgres + Docker). This is a snapshot of the shipped `settings.json` allow-list. | Full toolchain: python/uv/pip, node/npm/pnpm, dotnet, docker, psql, playwright, etc. |

**Steps:**

1. Choose your preset based on the repo's real tool surface. When in doubt,
   start with `restricted` and widen — an over-permissive preset is a risk;
   an under-permissive one is an annoyance.

2. Copy via the justfile recipe:

   ```bash
   just preset restricted       # or: just preset development
   ```

   The recipe confirms before overwriting an existing
   `.claude/settings.local.json`. It never modifies `settings.json` itself.

3. Restart Claude Code (or start a new session) for the new permissions to
   take effect. `settings.local.json` is loaded at session start.

4. **Never commit `.claude/settings.local.json`.** It is per-clone by
   design and may leak local user paths. The `.gitignore` excludes it.

**Authoring a new preset:**

1. Create `.claude/settings.presets/<name>.json` following the shape of the
   existing two. The top-level `_preset_meta` object is documentation —
   `name`, `description`, `source` (prior-art pointer), `tier`.
2. Use only the keys Claude Code supports (`permissions.allow`,
   `permissions.deny`, `permissions.ask`). Do **not** include `hooks` or
   `env` in a preset — those belong in the root `settings.json` and
   should be stable across tiers.
3. Add a row to the table above.

**Gotcha:** presets are copies, not includes. Updating
`.claude/settings.json` will not propagate to a preset file. If you change
the default allow-list, also update `development.json` to keep it in sync;
a future `just preset-diff <name>` recipe could automate this check.

---

## 9. Debug a failing verify_cmd

Short playbook, applied inside the `systematic-debugging` skill:

1. Read the JSONL trace for the failing subagent.
2. Isolate the minimal reproduction (one test, one file).
3. Form **three** hypotheses, not one. Rank by likelihood.
4. Test highest-likelihood hypothesis first with a printf/assertion.
5. Only after observation, propose the fix.
6. Re-run `verify_cmd`; on pass, commit atomically.
7. If 3 attempts fail, escalate (Constitution IX.1).

Never skip to step 5. The hook logs you; skipping is visible.

---

## 10. Add a new compliance rule

Use when the compliance team adds a domain class that has
engineering-level obligations (encryption, retention, logging) the
framework should enforce via injected rules. Example classes already
shipped: `lab-data`, `pii`, `phi`, `financial`.

**Prerequisites**
- The new domain class has distinct engineering guidance — not a
  policy statement only the compliance team reads.
- Some existing or planned Streck app has a reason to carry the flag.
- The guidance is stable (not a this-week memo).

**Steps**
1. **Pick the flag name.** Lowercase, kebab-case, single word where
   possible (`sox`, `gdpr`, `ccpa`, `export-control`). Avoid
   abbreviations that collide with stack names.
2. **Add the rule file.** Create
   `rules/compliance/<flag>.md`. Target length ~60-100 lines.
   Structure mirrors the existing four files: iron law → numbered
   sections (retention, logging, access, testing, red flags). Do not
   write legal advice; write the engineering operational posture.
3. **Extend the `ComplianceFlag` literal** in
   `schemas/intake_form.py`. The `Literal[...]` under `# ----- Field
   types -----` gains a new entry. Re-check the
   `_flags_are_consistent` validator — if your new flag should be
   mutually exclusive with `public`, update the validator. Write a
   test in `tests/test_intake_form.py` that asserts the exclusion.
4. **Register in the hook's allow-list.** Open
   `.claude/hooks/subagent_start.py` and add the flag to
   `COMPLIANCE_FLAGS_WITH_RULES`. Flags absent from this set are
   ignored (labelling only); flags present trigger file load.
5. **Add a row to `rules/compliance/README.md`** in the flag table,
   one-sentence "triggers on" cell that tells an operator when to
   tick the flag.
6. **Mention the flag in one intake example** (under
   `intake/examples/`). A flag with zero example coverage is a code
   smell — either a real app should need it soon, or the flag is
   premature.
7. **Run the hook locally.** Pipe a synthetic payload into
   `.claude/hooks/subagent_start.py` with `.soup/intake/active.yaml`
   carrying the new flag; assert the `additionalContext` response
   includes the rule file's first line. The hook fails soft, so a
   silent drop is the usual bug.

**What NOT to do**
- **Do not** extend `rules/global/*.md` with the new content. Global
  rules inject on **every** subagent regardless of domain;
  compliance rules are purposely conditional.
- **Do not** shadow stack rules. If a rule applies only to `.py`
  files, it belongs under `rules/python/`, not
  `rules/compliance/`.
- **Do not** rely on prose in the spec to trigger the rule. The
  lever is the typed `compliance_flags[]` enum, not free text.

Typical diff:

```
rules/compliance/<new-flag>.md         [new; ~80 lines]
rules/compliance/README.md             [+1 row in table]
schemas/intake_form.py                 [+1 enum literal]
tests/test_intake_form.py              [+1 test for exclusion / round-trip]
.claude/hooks/subagent_start.py        [+1 entry in COMPLIANCE_FLAGS_WITH_RULES]
intake/examples/<some-app>.yaml        [+flag in one realistic example]
```

No command or agent file changes — the hook is the enforcement
point, and the intake form is the capture point. Both are already
flag-aware.
