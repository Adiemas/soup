# disler/bowser

A four-layer agentic browser-automation framework: skill primitives,
subagent wrappers, orchestrator commands, and a justfile that exposes
each layer independently for targeted testing. The layering idea
generalizes well beyond browser work. Relevance rating: 4/5.

- URL: https://github.com/disler/bowser (representative)
- Research summary: `research/02-disler.md`

## What we took

- Four-layer callability: `skill → subagent → command → justfile`,
  each independently testable.
- Skill + subagent pairing — `@x-agent` calls `/x-skill`; decouples
  agent logic from tool logic.
- YAML story-driven testing (non-technical, versionable test cases)
  — informs our template-driven spec seed patterns.

Explicitly NOT copied: Bowser's full Playwright layer — only relevant
when we add browser-based UAT subagents, deferred per `DESIGN.md §10`.
