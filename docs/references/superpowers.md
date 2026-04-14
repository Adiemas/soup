# superpowers

Jesse Vincent's (obra) distribution of skills-as-iron-laws for Claude
Code. Each skill is a markdown file with YAML frontmatter describing
its triggers and a hard-coded procedural gate ("no X without Y
first"). Skills are the enforcement mechanism for TDD, verification,
and systematic debugging that makes Claude stop guessing and start
testing. Relevance rating: 5/5.

- URL: https://github.com/obra/superpowers
- Research summary: `research/04-superpowers.md`

## What we took

- `.claude/skills/<name>/SKILL.md` format — frontmatter +
  iron-law markdown body.
- The canonical skill set: `tdd`, `systematic-debugging`,
  `verification-before-completion`, `writing-plans`, `executing-plans`,
  `brainstorming`, `subagent-driven-development`,
  `dispatching-parallel-agents`, `using-git-worktrees`,
  `requesting-code-review`, `finishing-a-development-branch`.
- The "iron law" phrasing style for procedural gates (Constitution
  derives from this tone).
- Trigger-based skill invocation — the `user_prompt_submit` hook
  surfaces a skill when the user's prompt matches its triggers.
- Subagent-driven-development pattern — fresh subagent per task.
