# Scratchpad — Inter-agent Communication

_Append-only during a run. Orchestrator resets this file at the start of each ExecutionPlan run._

**Format:**

```
## [<wave>.<step>] <agent-name> @ <ISO-ts>
- finding: ...
- decision: ...
- handoff: ...
```

**Rules:**
1. Orchestrator truncates this file (keeping header) when it begins executing a new ExecutionPlan.
2. Specialists append after their step completes.
3. Reviewers read the full scratchpad for context.
4. Never include secrets, full prompts, or raw tool output — summarize.
5. Max 400 lines per run; orchestrator compacts older sections when approached.

---

_<scratchpad entries appear below this line>_
