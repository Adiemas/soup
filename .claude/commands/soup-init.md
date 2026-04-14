---
description: Scaffold a new internal app from a template. Templates — python-fastapi-postgres, dotnet-webapi-postgres, react-ts-vite, fullstack-python-react, nextjs-app-router, ts-node-script.
argument-hint: "<template> <app-name>"
---

# /soup-init

## Purpose
Bootstrap a new internal app in a sibling directory using a canonical template. Initializes CLAUDE.md, git, and runs `just init` in the new dir.

## Variables
- `$1` — template name (one of: `python-fastapi-postgres`, `dotnet-webapi-postgres`, `react-ts-vite`, `fullstack-python-react`, `nextjs-app-router`, `ts-node-script`).
- `$2` — app name (becomes new dir under parent of soup, or `SOUP_APPS_DIR` if set).

## Workflow
1. Validate template exists under `templates/<template>/`. Reject with list of available templates if not.
2. Compute target dir: `${SOUP_APPS_DIR:-../<app-name>}`. Abort if exists non-empty.
3. Copy tree: `templates/<template>/` → target, preserving `.gitignore`, etc.
4. Substitute placeholders: `{{APP_NAME}}` → `<app-name>`, `{{DATE}}`, `{{PYTHON_VERSION}}`, etc. (defined in `templates/<template>/.soup-template.json`).
5. In target:
   - `git init`
   - Copy `.env.example` to `.env` (empty values).
   - Write a project `CLAUDE.md` that references this soup repo for steering.
6. Run `just init` in target; report result.

## Output
- Target path.
- Files created count.
- `just init` exit status + log tail.
- Next step hint: `cd <target> && just go "<first goal>"`.

## Notes
- Templates are meant minimal-but-runnable. Heavy customization belongs in the new repo, not the template.
- Adding templates: see `docs/PATTERNS.md` → "Add a new template."
