# Spec-Driven Development & Agentic Testing — Research Report

## 1. GitHub Spec-Kit (Official)

**Purpose:** Reference SDD methodology for AI agents (Copilot, Claude Code, Gemini CLI, 24+ agents). Specs as "living, executable artifacts."

**Spec format:**
```markdown
# Task Management App Specification
## What to Build
Users should create projects, assign tasks, track progress with Kanban.
Real-time collaboration and mobile support required.
## Success Outcomes
- Real-time collaboration
- Instant Kanban updates
- Offline mobile
```

**Commands:** `/constitution` → `/specify` → `/clarify` → `/plan` → `/tasks` → `/implement`

**Patterns:**
- Intent-as-source-of-truth
- Separation of "what" (stable) from "how" (flexible)
- Validation gates between phases
- Four-phase forced structure

**Relevance: 5/5** — Official, 80K+ stars, agent-agnostic.

## 2. cc-sdd (gotalab)

**Purpose:** "Boundary-first spec discipline." Approved specs → long-running autonomous implementation with per-task fresh agents.

**Spec format:** EARS requirements ("The system shall..."), testable acceptance criteria, Mermaid designs, File Structure Plan, annotated tasks with boundaries/dependencies.

**Commands:** `/kiro-discovery` → `/kiro-spec-requirements` → `/kiro-spec-design` → `/kiro-spec-tasks` → `/kiro-impl` (RED→GREEN→debug loop) → `/kiro-steering`

**Patterns:**
- Explicit file structure planning drives task boundaries
- Per-task fresh implementers prevent context pollution
- TDD enforced (RED fails → GREEN passes)
- Task annotations enable parallel human-agent work
- Auto-debug on test failure

**Relevance: 5/5** — Most production-ready; team-ready; TDD-native.

## 3. Claude Code Spec Workflow (Pimzino)

**Purpose:** Streamlined SDD npm package for Claude Code. 60-80% token reduction via context optimization.

**Commands:** `/spec-create feature "desc"`, `/spec-steering-setup` (persistent vision/stack/structure), `/spec-execute`, `/spec-dashboard`. Separate bug-fix workflow.

**Patterns:**
- Steering documents for persistent context
- Context optimization for long sessions
- Dashboard transparency
- Separated bug-fix flow

**Relevance: 4/5** — Claude-specific, small teams.

## Agentic Testing Patterns

### Red/Green/Refactor
- **Red:** Write test, confirm failure (prevents false positives)
- **Green:** Minimum code to pass (no over-engineering)
- **Refactor:** Polish; test suite as safety net

**Why with agents:**
- Protects against speculative non-functional code
- Robust test suite emerges naturally
- Regression protection
- Clear pass/fail accountability

### Enforcement
- Per-task fresh agents (see only spec + tests)
- TDD gating (tests run before review; failure = auto-debug)
- Test-first instructions
- Single-assertion rule (one test = one behavior)

### TDAD (Test-Driven Agentic Development)
Graph-based impact analysis (AST + weighted code-test relationships). Results: 70% fewer test regressions, 32% better resolution rate. Specs include test suites as design artifact.

## Synthesis: Recommended SDD Flow for Soup

**Hybrid (cc-sdd foundation + Spec-Kit planning + Pimzino context):**

1. **Foundation:** constitution file (code structure, quality standards), EARS-style Markdown specs, file structure planning in design phase.
2. **Planning (Spec-Kit):** `/plan` generates architecture + tech. Becomes persistent steering.
3. **Tasks (cc-sdd):** Annotated boundaries + dependencies. Test file structure included.
4. **Implementation (cc-sdd + TDD):** Per-task fresh subagents. RED→GREEN→REFACTOR. Auto-debug on failure. Independent per-task review.
5. **Context (Pimzino):** Steering in CLAUDE.md. Dashboard via task output. Context optimization hooks.

**For Python/C#/React/TS:**
- CLI: `specify init <project>` → `/constitution` → `/specify` → `/plan` → `/tasks`
- Subagents: one per task; receives spec + test structure + scope
- Testing: RED/GREEN gates; test suite as spec artifact
- Review: per-task PR w/ spec compliance check

**Key wins:**
- Specs as executable contracts
- Fresh agents per task → no context rot
- TDD discipline baked in
- Steering persistence across sessions

## Sources
- github/spec-kit
- gotalab/cc-sdd
- Pimzino/claude-code-spec-workflow
- Simon Willison: Red/Green TDD
- Tweag: Agentic Coding Handbook TDD
- TDAD arxiv paper
