# Iter-2 dogfood — Brownfield Integration (damage-simulator on warhammer-40k)

**Date:** 2026-04-14
**Target repo:** `C:\Users\ethan\CodeProjects\warhammer-40k-calculator` (read-mostly)
**Framework under test:** `soup` at `C:\Users\ethan\AIEngineering\soup`
**Mode:** Propose-only. Stakeholder ask: "Add a damage-simulator REST endpoint
that extends the existing combat-calculator API (no fork) and integrates a
mock `ExternalBalance` REST service."
**Scope:** Simulation only. No changes to the warhammer repo; no changes to
core soup framework files. Artifacts live in
`mock-apps/brownfield-damage-sim/`.

---

## Target snapshot (existing repo scale + existing combat calc)

Large monorepo (iter-1 dogfood covered the full stack map; repeated
minimally here).

- **Backend entry surface:** `backend/app/main.py` mounts routers from
  `backend/app/api/` — 58 routes across `auth.py`, `calculations.py`,
  `community.py`, `ml.py`, `units.py`, `weapons.py`, `websocket.py`.
- **Existing combat-calculator core files:**
  - `backend/app/api/calculations.py` (~1200 lines; `POST /calculate`
    handler at lines 35-106; 50k-iteration cap at line 53).
  - `backend/app/services/combat_calculator.py` (~600 lines;
    `EnhancedCombatCalculator` with `_calculate_damage_distribution`
    private Monte Carlo loop at line 418; `calculate_scenario_async`
    orchestration at line 526).
  - `backend/app/schemas/combat.py` (`CombatModifiers` with `hit_modifier`,
    `wound_modifier`, `save_modifier` fields at lines 22-37 — the exact
    shape ExternalBalance returns. Happy accident, or the team already
    thought about it).
- **Existing test surfaces:** `backend/tests/test_combat_validation.py`,
  `backend/test_enhanced_calculator.py`, plus the root-level
  `tests/test_complete_backend.py`. Mix of in-tree and bespoke runners.
- **External REST infrastructure:** **none**. No `httpx` client anywhere
  under `backend/app/`. `backend/app/clients/` does not exist. Adding
  ExternalBalance is the repo's first external-REST dependency — the
  `contract-drift-detection` setup (OpenAPI + regen + `.hash`) is genuinely
  new to this codebase.

---

## Simulated /intake (propose `--brownfield` mode if needed)

Soup today has `/specify "<goal>"`, which implicitly assumes greenfield
intent — the `spec-writer` agent writes EARS requirements but has no
concept of "extends an existing spec" or "must preserve a byte-for-byte
contract." That framing matters for two reasons:

1. **Constitution Article I.4** says approved specs are frozen — changes
   require a new spec version. An extension spec (damage-sim) logically
   references the original spec (combat-calculator), but there is no
   `specs/combat-calculator*.md` in the warhammer repo to reference. It
   never went through soup.
2. **`rules/global/brownfield.md` iron law** says "Read existing code +
   tests BEFORE proposing changes." But `/specify` never dispatches the
   `researcher` agent — the spec is written blind. Then `/plan` is
   expected to compensate. That's too late: the spec itself leaks the
   "just fork the calculator" anti-pattern unless the spec-writer has
   been shown the existing code.

**Proposed additions (NOT implemented — belong on the framework
roadmap):**

- **`/specify --extends <existing-spec-path>`** — the spec-writer reads
  the referenced spec and must produce a spec whose `Functional
  requirements` section flags each FR as `[preserves]`, `[adds]`, or
  `[deprecates]` relative to the parent. Rejects specs that silently
  replace a parent FR without a `[deprecates]` marker.
- **`/intake --brownfield <repo-path>`** — a new command that runs the
  `researcher` agent FIRST (before `spec-writer`), produces a findings
  table saved to `.soup/research/<slug>-findings.md`, and **auto-hints
  that path into `spec-writer`'s context**. The spec-writer then writes
  a spec that cites concrete file+line coordinates from the research
  pass. Today you have to do this hand-off manually.

The mock-app `specs/damage-sim-2026-04-14.md` demonstrates the shape —
notably the `## Brownfield notes` section listing `Files touched
(planned)` and the `Extends:` pointer. That section is **not** in
`.claude/agents/spec-writer.md`'s required list; it's improvised. It
would be a natural fit under `--extends`.

---

## Simulated /plan (with context_excerpts excerpts quoted)

The researcher findings (see `mock-apps/brownfield-damage-sim/.soup/research/damage-sim-findings.md`)
supply the concrete anchors. The architect / `plan-writer` feeds them
into `context_excerpts` on each step. A representative sample, lifted
verbatim from the mock-app findings table:

| File | Line | Relevance | Excerpt |
|---|---|---|---|
| `backend/app/api/calculations.py` | 35-45 | primary — `POST /calculate` signature; new route mirrors this shape | `@router.post("/calculate", response_model=CombatResultResponse)` |
| `backend/app/api/calculations.py` | 53-57 | primary — existing 50_000 iterations cap; FR-7 reuses the same cap | `if request.scenario.iterations > 50000:` |
| `backend/app/services/combat_calculator.py` | 344-412 | primary — existing Monte Carlo loop `_calculate_damage_distribution` returning `probability_distribution[damage]` dict; S4 reuses this backbone, does NOT reimplement | `for _ in range(iterations): ...` |
| `backend/app/services/combat_calculator.py` | 526-540 | primary — `calculate_scenario_async` outer orchestration; S4 sits at the same layer but must not edit this | `iterations = min(scenario_data.get('iterations', settings.DEFAULT_MONTE_CARLO_ITERATIONS), ...)` |
| `backend/app/schemas/combat.py` | 18-58 | primary — `CombatModifiers`; S5 applies ExternalBalance `hit_modifier` onto this | `hit_modifier: int = Field(0, ge=-3, le=3, ...)` |
| `backend/app/services/combat_calculator.py` | 17-18 | secondary — existing `httpx`? **no** — calculator imports `redis.asyncio`. No `httpx.AsyncClient` anywhere. | `import redis.asyncio as redis` |
| `backend/app/clients/` | — | missing — directory does not exist; S2 creates it, `contract-drift-detection` skill applies | _(absent)_ |

**Key architectural decisions the plan encodes:**

1. **Extension by composition, not fork.** S4 wraps the existing private
   `_calculate_damage_distribution` — does not edit
   `calculate_scenario_async`. Preserves AC-2 (byte-for-byte `/calculate`
   response).
2. **New surface, same router.** S5 adds the new endpoint to the same
   `APIRouter` instance. No new module for the route — consistent with
   the repo's existing convention.
3. **Contract-drift harness first, client after.** S2 runs before S3
   (test-engineer) because the client file doesn't exist until S2
   regenerates it. The `.hash` file starts as `PLACEHOLDER-run-regen...`
   and S2 populates it.
4. **Regression-baseline step (S6) is explicit.** Soup today has no
   automatic regression-baseline mechanism; S6 invokes `verifier` with a
   diff against `.soup/baseline/backend-tests.txt`. See gap list.

---

## Simulated /tasks (link to .soup/plan.json you wrote)

Plan: `mock-apps/brownfield-damage-sim/.soup/plan.json` (8 steps,
validated against `schemas/execution_plan.py::ExecutionPlan`).

Wave structure (derived from `depends_on`):

- **Wave 1:** S0 (researcher) — haiku; sets up `context_excerpts`.
- **Wave 2:** S1 (test-engineer RED `/calculate` + distribution), S2
  (full-stack-integrator contract-drift) — parallel.
- **Wave 3:** S3 (test-engineer RED external-balance) — depends on S2.
- **Wave 4:** S4 (python-dev GREEN calculator).
- **Wave 5:** S5 (python-dev GREEN route wiring).
- **Wave 6:** S6 (verifier regression-baseline).
- **Wave 7:** S7 (qa-orchestrator brownfield QA gate).

Validation output when I ran the plan through the real schema:

```
OK: Extend combat-calculator API with a damage-simulator endpoint...
steps: ['S0', 'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7']
  S0 | agent= researcher        | ce= 1 | sr= 1
  S1 | agent= test-engineer     | ce= 4 | sr= 1
  S2 | agent= full-stack-integr | ce= 2 | sr= 1
  S3 | agent= test-engineer     | ce= 3 | sr= 1
  S4 | agent= python-dev        | ce= 3 | sr= 1
  S5 | agent= python-dev        | ce= 4 | sr= 1
  S6 | agent= verifier          | ce= 1 | sr= 1
  S7 | agent= qa-orchestrator   | ce= 1 | sr= 1
```

Every non-research step has `context_excerpts` populated — this is where
the researcher's coordinates land and the reason this new field exists
in `schemas/execution_plan.py`. Without it, S1's `test-engineer` would
ask "where does `/calculate` live?" again and burn part of its 10-turn
budget on Grep.

The RED-phase steps (S1, S3) use a leading `! ` on `verify_cmd` per
`execution_plan.py` line 88's note ("A leading `! ` prefix inverts the
exit code (TDD RED-phase)"). That is the current mechanism — no
`verify_expects: "fail"` field exists, which was a flagged sharp edge
in iter-1.

## Walked TDD pairs (S1 → S4)

Files written under `mock-apps/brownfield-damage-sim/`:

- **RED** (`backend/tests/test_distribution_simulator.py`) — three
  tests:
  - `test_calculate_response_hash_unchanged` — characterization test
    for AC-2. Hashes the canonical scenario response and compares to a
    frozen baseline. Today the baseline is a sentinel
    (`CHARACTERIZATION_HASH_SENTINEL`), so it fails deterministically.
  - `test_simulate_distribution_returns_full_shape` — drives FR-2 and
    S4's new method. Asserts keys `{distribution, percentiles, mean,
    variance, iterations_run}` and that `distribution` probabilities
    sum to ≈1.
  - `test_simulate_distribution_is_deterministic_with_seed` — seed
    reproducibility, so regression tests don't flake.
- **GREEN shim** (`backend/src/damage_sim/calculator.py`) — a toy
  `EnhancedCombatCalculator.simulate_distribution` that exercises the
  test harness (sampler → Counter → percentiles → dict). Explicitly
  marked as "NOT the real feature" in its module docstring; the real
  implementation reuses the private `_calculate_damage_distribution` at
  `combat_calculator.py:418` instead of reimplementing the sampler.

The point of the walk: confirm that the `context_excerpts` machinery,
the `! ` RED-prefix convention, and the fresh-subagent boundary all fit
the brownfield shape. They do — with the gaps noted below.

---

## full-stack-integrator usefulness here

Cycle-1 introduced `full-stack-integrator` to fix "python-dev and react-dev
each see half a contract." For this feature the "cross-stack" is
different: it's **this service** ↔ **ExternalBalance**. That's the same
shape (OpenAPI ↔ Python client instead of OpenAPI ↔ TS types), and the
agent already covers it — its Process step #3 says "Run the documented
regen script verbatim; if no regen script exists, surface this as a
blocker and escalate rather than inventing one."

**S2 walks the `contract-drift-detection` 4-phase loop against the mock-app:**

1. **Detect** — `backend/app/clients/` directory does not exist; the
   OpenAPI spec at `contracts/external-balance.openapi.yaml` is freshly
   introduced; no regen script is documented in the warhammer repo's
   `package.json` or `pyproject.toml`. This is exactly the "repo gap"
   case the skill's Phase 1 #3 says to surface.
2. **Compare** — `external-balance.openapi.yaml.hash` currently holds
   the sentinel `PLACEHOLDER-run-regen-script-to-populate`. First run of
   S2 replaces it with a real sha256.
3. **Regenerate** — S2 runs `just regen-clients` (doesn't exist yet in
   the target repo; the agent escalates). In a clean setup, this is a
   one-liner wrapping `openapi-python-client generate --path contracts/external-balance.openapi.yaml --custom-template-path ...`.
4. **Verify** — both sides build: backend pytest + an import-smoke test
   for the generated client.

**The real usefulness signal here** is that Streck controls both the
damage-sim service and the ExternalBalance contract (per the ask). So
the source-of-truth flow is clean: edit the YAML, run the regen, the
Python client re-renders, both sides' tests run. The agent's "source of
truth drives dependents, never the reverse" iron law maps 1:1.

If Streck did **not** control ExternalBalance, `full-stack-integrator`'s
job would flip: hash the upstream OpenAPI URL, auto-PR when it changes,
add a runbook for the expected change cadence. That variant is a
**proposed enhancement**, not a gap in the current role.

---

## Gap list — what soup misses for brownfield

### 1. `/intake --brownfield <repo-path>` (MISSING)

Today `/specify` dispatches `spec-writer` directly. There is no command
that runs the `researcher` agent first to seed the spec with concrete
coordinates. You can work around it by invoking `researcher` manually
and pasting the findings into `$ARGUMENTS`, but that loses the
`context_excerpts` chain.

**Observed cost:** S0 in the mock plan is doing what `/intake
--brownfield` would do automatically. The plan-writer has to know to
include a researcher step. A newer contributor would skip it and the
downstream `test-engineer` / `python-dev` steps would burn turns
rediscovering file locations.

### 2. `/specify --extends <existing-spec>` (MISSING)

Constitution I.4 freezes approved specs. Extension specs need a way to
reference the parent without re-specifying its FRs, and to explicitly
mark each new FR as `[preserves]` / `[adds]` / `[deprecates]` relative
to the parent. Today the spec-writer card has no section for this;
the mock-app spec improvises a `## Brownfield notes` tail section.

### 3. Researcher → `context_excerpts` auto-hint (MISSING)

The new `context_excerpts` field on `TaskStep` is well-designed, but
there is **no plumbing from `researcher` output into `context_excerpts`
on downstream steps.** Today the plan-writer has to read the
researcher's findings table and manually populate each `TaskStep`. An
automation hint: every row in the researcher's findings table with
`relevance == "primary"` should become a `context_excerpts` entry on the
relevant downstream step, keyed by the step's `prompt` overlap. Add a
script at `scripts/hydrate-context-excerpts.py` or a hook in
`meta-prompter`.

### 4. "Existing API contract snapshot" artifact (MISSING)

`contract-drift-detection` assumes a contract source-of-truth **exists**.
For the warhammer repo, **there is no pre-snapshot OpenAPI**. FastAPI
generates an OpenAPI at runtime (`/docs`), but it isn't checked in. So
there's no baseline for contract-drift to compare against. Two fixes:

- **Soft:** a skill/runbook ("freeze existing API to OpenAPI pre-edit") —
  invoke it once before the first brownfield edit lands.
- **Hard:** a framework step that, on first `/plan` against a
  brownfield FastAPI repo, runs `python -m app.main --print-openapi >
  contracts/<service>.openapi.yaml` and checks it in. The hash then
  guards byte-for-byte preservation across unrelated edits (stronger
  than AC-2's response-body hash).

### 5. Deprecation policy guidance in `rules/global/` (MISSING)

`rules/global/brownfield.md` covers "read existing code" and "when
existing behaviour is wrong." It does **not** say:

- How to mark an FR as deprecated (HTTP `Deprecation` header? `X-API-Deprecated-At`?
  docstring convention? `warnings.warn` in the Python path?).
- What the removal horizon is (one minor version? one sprint?
  stakeholder sign-off?).
- How to tell a downstream client that a field is deprecated (OpenAPI
  `deprecated: true`? TS `@deprecated` JSDoc?).

Without it, brownfield changes that **should** deprecate something
silently break callers or leave dead code forever.

**Suggested file:** `rules/global/deprecation.md` — short, opinionated:
"minimum 1 minor version window; HTTP `Deprecation` + `Sunset` headers;
`openapi.deprecated: true`; `warnings.warn(stacklevel=2)` in Python
internal callers."

### 6. "Existing test suite must still pass" — automatic vs explicit? (HALF-THERE)

The constitution says every step has a `verify_cmd`, but a per-step
`pytest backend/tests/ -k distribution` does **not** re-run the
thousands of other backend tests. So a brownfield edit that passes its
own scope's `verify_cmd` can silently break `test_auth.py`,
`test_community.py`, etc.

Two paths to fix:

- **Per-plan `regression_baseline_cmd`** on `ExecutionPlan` (new field).
  Orchestrator runs it once before S1 and once after the final step;
  diffs the pass/fail sets. This is what the mock-app's S6 does
  manually.
- **Per-step "also run the inherited baseline" flag** on `TaskStep` —
  e.g. `verify_inherits_baseline: true`. Slower but safer; orchestrator
  could parallelize the inherited run.

Today the mock-app plan encodes S6 as an explicit `verifier` step.
It works, but every plan author has to remember to add it. A framework
default would close the hole.

### 7. `files_allowed` in brownfield (WORKS, WITH CAVEATS)

`pre_tool_use` hook enforces `files_allowed` per-step, which **is** the
right primitive for brownfield. But brownfield wants **line-range**
scoping too: "you may edit `calculations.py` but NOT the byte-range
[35-106] which is the preserved `/calculate` handler." Today the only
way to enforce this is a characterization hash (S7 in the mock plan).
A `files_allowed` with `{path, excluded_line_range}` entries would be
stronger — the hook could reject the edit at write time instead of the
QA gate catching it after.

---

## Proposed soup additions (file-level)

1. **`.claude/commands/intake.md`** — new command. Arg: `--brownfield
   <repo-path>`. Runs `researcher` → writes findings to
   `.soup/research/<slug>-findings.md` → dispatches `spec-writer` with
   that path auto-injected into `$ARGUMENTS`. Greenfield path dispatches
   `spec-writer` directly (same as today's `/specify`).

2. **`.claude/commands/specify.md`** — extend to accept `--extends
   <spec-path>`. When set, spec-writer is handed the parent spec and
   must produce a spec whose FRs carry `[preserves]/[adds]/[deprecates]`
   tags. Keep the agent card (`spec-writer.md`) as single source of
   truth per the command's current note.

3. **`rules/global/deprecation.md`** — new file. Horizon policy
   (minimum 1 minor version), HTTP headers (`Deprecation`, `Sunset`),
   OpenAPI `deprecated: true`, Python `warnings.warn(stacklevel=2)`, JS
   `@deprecated` JSDoc. Under 60 lines.

4. **`schemas/execution_plan.py`** — add optional top-level
   `regression_baseline_cmd: str | None` on `ExecutionPlan` with a
   docstring explaining orchestrator behaviour (run once pre-S1 and
   once post-final; diff pass/fail). No change to `TaskStep` required.

5. **`scripts/hydrate_context_excerpts.py`** — new helper. Reads the
   most recent `.soup/research/<slug>-findings.md`, parses the findings
   table, and produces a patch for `.soup/plans/<slug>.json` that
   populates `context_excerpts` on every step whose `prompt` matches a
   finding's `relevance` keyword. Invoked by `meta-prompter` between
   plan emit and `ExecutionPlanValidator.validate()`.

6. **`.claude/skills/brownfield-baseline-capture/SKILL.md`** — new
   skill. 3-phase: (1) enumerate existing routes / test-passes; (2)
   freeze to checked-in artifacts (OpenAPI yaml + `.soup/baseline/tests.txt`);
   (3) hash both. Invoked once per brownfield repo, idempotent on
   re-run. Closes Gap #4 and Gap #6.

7. **`docs/runbooks/brownfield-first-edit.md`** — new runbook. Symptom:
   "stakeholder says 'extend X' on a repo that hasn't been soup-ified."
   Fix: run `brownfield-baseline-capture` skill → `/intake
   --brownfield` → `/specify --extends` (if a parent spec was
   captured by the baseline) → standard `/plan → /tasks → /implement`.

8. **`.claude/agents/full-stack-integrator.md`** — one-line addendum
   under "When invoked": "Service-to-external-REST contract boundaries
   count. OpenAPI → Python client (httpx / openapi-python-client) is
   the same shape as OpenAPI → TS types." The agent already does this
   in practice; making it explicit avoids a plan-writer thinking the
   role is frontend-only.

9. **`rules/global/brownfield.md`** — add a new subsection
   "Line-range preservation" referencing the characterization-hash
   pattern (S1 in the mock plan). Worth naming it so it isn't
   re-invented every time. Under 20 lines.

10. **`.claude/agents/plan-writer.md`** — update to state that if the
    spec has a `## Brownfield notes` section (or was produced via
    `/specify --extends`), the plan MUST start with a `researcher` step
    (S0 pattern) and at least one step with `agent: verifier` and a
    regression-baseline comparison. Currently unspoken; a contributor
    could skip both without the schema complaining.

---

## Artifacts produced by this walk

- `mock-apps/brownfield-damage-sim/specs/damage-sim-2026-04-14.md` —
  the extension spec, improvised `## Brownfield notes` section.
- `mock-apps/brownfield-damage-sim/contracts/external-balance.openapi.yaml` +
  `.hash` — OpenAPI source of truth + (sentinel) hash marker for S2.
- `mock-apps/brownfield-damage-sim/.soup/plan.json` — 8-step
  `ExecutionPlan`, validated against `schemas/execution_plan.py` (every
  step has `context_excerpts` + `spec_refs`).
- `mock-apps/brownfield-damage-sim/.soup/research/damage-sim-findings.md` —
  the researcher findings table that seeded `context_excerpts`.
- `mock-apps/brownfield-damage-sim/backend/tests/test_distribution_simulator.py` —
  the RED-phase characterization + new-feature tests (S1).
- `mock-apps/brownfield-damage-sim/backend/src/damage_sim/calculator.py` —
  the shim GREEN implementation (S4 sketch; NOT the real feature).

Zero edits to the warhammer repo. Zero edits to core soup framework
files.
