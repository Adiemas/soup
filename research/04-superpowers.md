# Superpowers — Research Report

## Purpose
Comprehensive workflow system transforming agents from code-first to specification-first. Decomposes dev into mandatory procedural skills: brainstorming, design validation, TDD, systematic debugging, verification. Enforces discipline: no code before design approval, no implementation before written plan, no prod code without failing tests, no bug fixes without root cause.

## Skill Format

YAML-frontmatter markdown with three fields:

```yaml
---
name: test-driven-development
description: Use when implementing any feature or bugfix, before writing implementation code
---

# Test-Driven Development (TDD)
[overview, iron law, process flows, steps, examples, red flags, quick reference, related skills]
```

Skills contain:
- **Overview** (1-2 sentences core principle)
- **Iron Law** (non-negotiable rule, triple-backticks)
- **Process flows** (dot-format decision diagrams)
- Step-by-step with examples + anti-patterns
- **Red Flags** table (rationalizations → reality)
- Quick-reference tables
- **Related skills** cross-references
- Supporting files (e.g., `implementer-prompt.md`, `spec-document-reviewer-prompt.md`)

## Key Skills Catalog

**Collaborative Design (Pre-Code):**
- `brainstorming` — Socratic questioning, 2-3 alternatives, validated design sections before any implementation
- `writing-plans` — approved designs → bite-sized tasks (2-5 min each) with exact file paths, code blocks, verification commands

**Implementation:**
- `test-driven-development` — RED-GREEN-REFACTOR enforcer; deletes code written before tests; mandatory red/green verification
- `subagent-driven-development` — fresh subagent per task; two-stage review (spec compliance → code quality)
- `executing-plans` — batch task execution with human checkpoints

**Reliability & Debugging:**
- `systematic-debugging` — 4-phase root cause (investigate → pattern analysis → hypothesis → implementation); hard block on guessing; escalates to architecture review after 3 failed attempts
- `verification-before-completion` — gate: identify verify command → run fresh → read output → verify claim; blocks on missing evidence

**Collaboration:**
- `dispatching-parallel-agents` — concurrent subagent dispatch; groups failures by domain
- `using-git-worktrees` — per-feature branches, isolated workspaces
- `requesting-code-review` — pre-review checklist (spec compliance first, code quality second)

**Lifecycle:**
- `finishing-a-development-branch` — verifies tests pass, presents merge/PR/discard
- `using-superpowers` — meta-skill establishing mandatory invocation (even 1% applicability = must invoke)

## Patterns Worth Stealing

1. **Mandatory Procedural Gates** — skills override default behavior; "if a skill applies, you do not have a choice"
2. **EXTREMELY-IMPORTANT directives** — raw enforcement for critical discipline
3. **Red Flags tables** — rationalizations → reality checks; prevents self-talk-out
4. **Iron Law formulation** — single absolute rule (e.g., "NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST")
5. **Two-stage review** — spec compliance + code quality as separate passes
6. **Subagent isolation** — fresh context per task
7. **Bite-sized tasks** — 2-5 min granularity for visible progress
8. **Verification-first evidence** — "evidence before claims always"

## Patterns to Adapt

1. **Skill triggering** — soup can be more permissive (optional, intent-triggered vs. mandatory)
2. **Decision-tree diagrams** (dot format) for markdown readability
3. **Plan document templates** — headers, task structure, checkbox syntax
4. **Spec-Review → Plan-Write → Task-Execute pipeline** as distinct phases
5. **External technique files** — reference `root-cause-tracing.md`, `condition-based-waiting.md` vs. embedding everything

## Skills vs. Hooks/Commands

Command-driven, not hook-driven. Platform-specific Skill tools (Claude Code `Skill`, Copilot `skill`, Gemini `activate_skill`). No persistent state; activate on agent decision.

**For soup decision:**
- **Reactive** (user keyword/intent trigger)
- **Proactive** (agent self-triggers based on task type) ← superpowers uses this
- **Hook-based** (file mod, test failure, git event)

## Relevance: 5/5

**Transferable to soup:**
1. Skill-as-workflow-primitive — dispatch skills vs. inline reasoning
2. Procedural discipline — non-negotiable workflows
3. Subagent composition — `subagent-driven-development`, `dispatching-parallel-agents`
4. Evidence-based verification
5. Plan → task decomposition (`writing-plans` → `executing-plans`)

**Caution:** Superpowers assumes single agent with skill invocation; soup involves multi-agent coordination. Adapt to include inter-agent comms, shared plan execution, distributed dispatch.

**Local install:** `C:\Users\ethan\.claude\plugins\cache\claude-plugins-official\superpowers\5.0.7\` — 12 core skills, supporting docs, agent prompts (implementer, spec-reviewer, code-quality-reviewer).
