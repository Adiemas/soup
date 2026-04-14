---
name: agentic-rag-research
description: Use when a task requires non-trivial org-specific knowledge that lives in the RAG index. Runs an autoresearch-style retrieve-synthesize-follow-up loop with cited answers.
---

# Agentic RAG Research

## Overview
For any question that depends on org knowledge (internal wikis, prior decisions, repos), dispatch `rag-researcher` to run a bounded autoresearch loop: query → retrieve → synthesize → generate follow-ups → retrieve again → synthesize. Every factual claim is cited `[source:path#span]`.

## Iron Law
```
EVERY FACTUAL CLAIM MUST CARRY A [source:path#span] CITATION. UNCITED CLAIMS ARE DELETED.
```

## Process

1. **Scope the question.** One research question per dispatch. Multi-part questions get split.
2. **Declare a depth budget.** Default 3 loops. Deep dives authorize 5. More than 5 is probably re-scoping, not research.
3. **Dispatch `rag-researcher`** with: the question, optional scope filter (`github:`, `ado-wiki:`, `fs:`, `web:`), depth budget.
4. **Researcher loop:**
   - Formulate 2-4 angle queries
   - Call `rag/search.py --query <q> --top-k 8 --filter <scope>`
   - Read top chunks, extract facts, note gaps
   - Generate follow-ups for gaps; iterate up to budget
5. **Synthesize.** Bullet answer with inline citations. Evidence table. Gaps section.
6. **Validate citations.** Every bullet has at least one `[source:path#span]`. Paraphrases accurate to the source span.
7. **Feed results** into downstream spec/plan/task work. Attach the research report as context.

## Red Flags

| Thought | Reality |
|---|---|
| "I know this — skip RAG." | The corpus is the audit trail; your memory is not. Go through `rag/search.py`. |
| "One source is enough for a load-bearing claim." | Seek corroboration or flag explicitly as single-sourced. |
| "Paraphrase loosely to fit the narrative." | If the cite no longer supports the claim, re-retrieve verbatim. |
| "Research loop ran to budget; one more to be sure." | Stop. Report the gap honestly. More loops ≠ better answers. |
| "Claim without citation — reader can trust me." | Constitution VII.3: delete or cite. No exceptions. |

## Feeding research into `TaskStep.context_excerpts`

Research findings rarely live in isolation. When a `/plan` or `/tasks`
step needs the same Streck-internal knowledge you just retrieved,
you (or `tasks-writer`) must flow citations into
`TaskStep.context_excerpts` so the next subagent receives them
verbatim — without having to re-run the same search.

### The two citation worlds

| Source | Citation shape | Where it can flow |
|---|---|---|
| **Local repo file** | `specs/auth.md#design`, `src/api/auth.py:45-89` | Directly into `context_excerpts` (resolved by `agent_factory._compose_brief`). |
| **RAG retrieval** (GitHub blob, ADO wiki page, web doc) | `[github://streck/auth-service/src/lib/jwt.py#42-58]` or `[ado://streck/Security/wiki/AuthFlow.md#0-0]` | NOT directly resolvable today — `agent_factory._safe_relative_path` rejects URI schemes. You must materialise the snippet locally first. |

### Pattern: research → materialised excerpt → context_excerpts

When `rag-researcher` returns a hit you want to thread into the next
TaskStep:

1. Note the citation tag from the hit (e.g. `[github://streck/auth-service/src/lib/jwt.py#42-58]`).
2. Decide if the snippet is small enough to inline (~200 lines or
   under). If so, write it to a project-relative scratch file —
   conventionally `.soup/research/<slug>/<source-slug>.md`. Include a
   provenance header:

   ```markdown
   # Excerpt: streck/auth-service src/lib/jwt.py L42-58
   _Retrieved 2026-04-14 via `rag/search.py --query "JWT validation"`._
   _Original citation: [github://streck/auth-service/src/lib/jwt.py#42-58]_

   ```python
   def validate_token(token: str) -> Claims:
       # ... verbatim RAG-retrieved code ...
   ```
   ```

3. Now reference *the local materialised file* in
   `TaskStep.context_excerpts`:

   ```json
   {
     "id": "impl-S2-auth",
     "agent": "python-dev",
     "context_excerpts": [
       ".soup/research/new-login/auth-service-jwt.md"
     ],
     "spec_refs": ["specs/new-login-2026-04-14.md"]
   }
   ```

4. Commit the materialised excerpt (it is a project artifact,
   reproducible from the RAG citation). The
   `ExecutionPlanValidator._check_context_paths_exist` check will
   reject any plan that references a missing path, so the file MUST
   exist on disk at validation time.

### When NOT to materialise

- The hit is large (>500 lines): summarise into a research note
  that itself cites the RAG span, then thread the note in.
- The hit is org-public knowledge with high churn (e.g. an external
  vendor doc): keep it as an `rag_queries` entry on the TaskStep
  instead — the orchestrator will re-run the query at spawn time and
  inject fresh results.
- The hit is a one-off pointer for a single throwaway step: cite it
  in the prompt body, do not materialise.

### Output contract for the researcher

In addition to the markdown report, the researcher MUST emit a final
section:

```markdown
## Excerpts ready for `context_excerpts`

| Local path | Citation source | Suggested step IDs |
|---|---|---|
| `.soup/research/new-login/auth-jwt.md` | `[github://streck/auth-service/src/lib/jwt.py#42-58]` | `impl-S2-auth`, `test-S2-auth` |
```

`tasks-writer` reads this table and threads the `Local path` entries
straight into the `context_excerpts` of the named steps.

## Related skills
- `brainstorming` — often needs RAG first for org context
- `meta-prompting` — `rag_queries` can be run before each step
- `spec-driven-development` — research feeds the spec
