# mock-apps/

Throwaway internal apps built *by* the soup framework *on* the soup
framework. This is how we dogfood: every framework change gets
exercised end-to-end by running `just go` to produce a small,
realistic app in here, then running the three-reviewer panel over
the resulting artifacts.

---

## Purpose

1. **Framework regression detection.** If a change to
   `.claude/agents/`, `schemas/`, `rules/`, or the orchestrator
   breaks a real-world flow, the mock-app will notice before real
   Streck apps do.
2. **Reviewer feedback surface.** Each mock app carries a
   `FEEDBACK.md` — a structured critique from the reviewer panel
   pointing at friction, missing pieces, broken contracts, and
   sharp edges encountered while producing the app. These are the
   primary input to `soup`'s own review-and-patch cycle (see
   `docs/PATTERNS.md §8`).
3. **Teaching material.** New engineers can read a mock app +
   its `FEEDBACK.md` + its `specs/` + its `.soup/plans/` and see an
   end-to-end soup run, fully reified.

Mock apps are **framework dogfooding, not production code.** They
are not deployed, not maintained, and not meant to be copied into
real Streck services. If you want to ship a service for real, use
`just new <template> <name>` to scaffold into a sibling directory
(outside `mock-apps/`) — templates are in `templates/`.

---

## How to explore

```bash
cd mock-apps/<name>
cat FEEDBACK.md              # reviewer notes (start here)
ls specs/                    # the spec that drove the run
ls .soup/plans/              # the ExecutionPlan(s) the orchestrator executed
# app source lives in the usual subdirectory (backend/, frontend/, etc.)
```

`FEEDBACK.md` is the fastest path to understanding **what worked,
what didn't, and what the framework got wrong** on this cycle.

---

## Naming convention

One directory per mock app, kebab-case, describing the app's domain:

- `prompt-library/` — prompt storage + retrieval service
- `health-endpoint/` — minimal FastAPI with `/health` liveness probe
- `payroll-digest/` — nightly email summary of pipeline failures

Do **not** include the stack in the name (`prompt-library`, not
`prompt-library-fastapi`) — the stack is an implementation detail
chosen by the meta-prompter and visible in the spec.

The review cycle appends a date suffix to the `FEEDBACK.md` front
matter (not the directory name). If you iterate on the same mock
app, commit the new `FEEDBACK-YYYY-MM-DD.md` alongside the original
rather than overwriting — reviewer history is load-bearing for the
retrospective.

---

## Adding a new mock app

1. Pick a goal roughly the size of a real Streck feature —
   something that touches a spec, a migration, a test, and one or
   two endpoints. Too small (a one-liner) exercises `/quick`, not
   the full flow. Too large (a service with five bounded contexts)
   makes reviewer fatigue noisy.
2. Create `mock-apps/<name>/` and drop a `GOAL.md` at its root
   describing the natural-language ask in 3–10 sentences.
3. Run the framework end-to-end:

   ```bash
   just go "$(cat mock-apps/<name>/GOAL.md)"
   ```

4. Once the QA gate approves, dispatch the three-reviewer panel
   per `docs/PATTERNS.md §8`. Each reviewer writes their section of
   `FEEDBACK.md`. Commit everything — spec, plan, source, feedback.
5. If reviewers surface framework bugs (agent contracts misaligned,
   rules missing, commands ambiguous), file them as patches against
   soup itself, not against the mock app. The mock app is a
   *measurement*, not a product.

---

## Disclaimer

**Nothing under `mock-apps/` is production code.** There are no
SLAs, no on-call, no security review, no versioning guarantees.
Treat these directories as read-only artifacts of a framework test
run. If a mock app passes its own tests, that is a statement about
soup, not about the mock app being fit for deployment.

Do not import from, depend on, or extend any `mock-apps/*` code in
a real Streck service. Use `templates/` instead.
