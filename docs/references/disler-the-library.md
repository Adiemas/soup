# disler/the-library

A meta-skill distribution pattern: a single `SKILL.md` plus a
`library.yaml` catalog that references canonical skill/agent sources
in upstream repos. Skills are pulled on demand via `/library use <name>`
rather than vendored. Relevance rating: 5/5 — this is how soup stays
in sync with upstream superpowers without copying.

- URL: https://github.com/disler/the-library (representative)
- Research summary: `research/02-disler.md`

## What we took

- `library.yaml` as the single catalog of every skill, agent, and
  prompt with explicit `source:` and `upstream:` URLs.
- Typed dependency resolution (`requires: [skill:name, agent:name]`)
  — the catalog is a graph, not a list.
- Reference-based distribution: source of truth lives upstream,
  local copies are caches.
- `/library use <name>` command pattern — pull → cache → install into
  target project without a build step.
- No-build, markdown-only distribution. Agent-agnostic.
