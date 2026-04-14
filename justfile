# Soup — three-mode developer CLI
# ──────────────────────────────────────────────────────────────
# Patterns: disler install-and-maintain (three-mode), gsd (dev
# velocity), The Library (distribution). See docs/DESIGN.md §9.
#
# Modes:
#   deterministic → `just plan "<goal>"`    (meta-prompter dry-run)
#   supervised    → `just go   "<goal>"`    (plan + execute + QA)
#   interactive   → `just go-i "<goal>"`    (HITL at wave boundaries)

set shell := ["bash", "-cu"]
set dotenv-load := true
set positional-arguments

# Default recipe — show the menu.
default: help

# List every available recipe with its summary.
help:
    @just --list

# ── Bootstrap ────────────────────────────────────────────────

# Install deps (uv preferred, else pip), create venv, start postgres,
# stub secrets, bootstrap hooks. Idempotent.
init:
    @echo "[init] bootstrapping soup dev env"
    @if ! command -v just >/dev/null 2>&1; then echo "just is required" >&2; exit 1; fi
    @if command -v uv >/dev/null 2>&1; then \
        echo "[init] using uv"; \
        uv venv --python 3.12 .venv; \
        uv pip install -e ".[dev]"; \
    else \
        echo "[init] uv not found - falling back to pip"; \
        python -m venv .venv; \
        . .venv/bin/activate 2>/dev/null || . .venv/Scripts/activate; \
        python -m pip install --upgrade pip; \
        python -m pip install -e ".[dev]"; \
        venv_py=".venv/bin/python"; \
        [ -x "$venv_py" ] || venv_py=".venv/Scripts/python"; \
        if [ ! -x "$venv_py" ]; then \
            echo "[init] WARNING: could not locate venv python" >&2; \
        else \
            active_py="$(command -v python 2>/dev/null || echo)"; \
            case "$active_py" in \
                *"$PWD"/.venv*) echo "[init] venv active";; \
                *) echo ""; \
                   echo "[init] NOTE: pip-fallback does not persist venv activation between just recipes."; \
                   echo "        If you do not have uv installed, activate the venv manually before running just test / just go:"; \
                   echo "          - Git Bash / Linux / macOS:  source .venv/bin/activate"; \
                   echo "          - Windows cmd:                .venv\\\\Scripts\\\\activate.bat"; \
                   echo "          - Windows PowerShell:         .venv\\\\Scripts\\\\Activate.ps1"; \
                   echo "        Or install uv (recommended) to skip this step:  winget install astral-sh.uv  (Windows) / brew install uv (macOS)"; \
                   echo "";; \
            esac; \
        fi; \
    fi
    @if [ ! -f .env ]; then \
        cp .env.example .env; \
        echo "[init] stubbed .env — fill in secrets before use"; \
    fi
    @mkdir -p .soup/plans .soup/runs .soup/memory .soup/worktrees logging/agent-runs
    @if command -v docker >/dev/null 2>&1; then \
        echo "[init] starting postgres via docker compose"; \
        docker compose -f docker/docker-compose.yml up -d postgres || true; \
    else \
        echo "[init] docker not found — skip postgres (install docker & rerun just init)"; \
    fi
    @just install
    @just install-hooks
    @echo ""
    @echo "════════════════════════════════════════════════════════════════"
    @echo " soup is installed."
    @echo ""
    @echo "  - Claude Code hooks   → .claude/settings.json loaded"
    @echo "  - Git pre-commit hook → .githooks/pre-commit (secret scan, Art. VI.3)"
    @echo "  - Postgres            → docker compose up -d postgres (if docker present)"
    @echo "  - Venv                → .venv/"
    @echo ""
    @echo " Verify everything with:  just doctor"
    @echo " First run:               just go \"build me a health endpoint\""
    @echo "════════════════════════════════════════════════════════════════"

# Bootstrap hooks + .claude/settings.json linkage (disler three-mode).
# mode=hil prints the interactive-mode banner.
install mode="":
    @echo "[install] registering hooks from .claude/settings.json"
    @python -m orchestrator.cli install {{mode}}

# Install the git pre-commit secret scanner (Constitution VI.3).
# Points core.hooksPath at .githooks/ so every commit runs the scan.
install-hooks:
    @echo "[install-hooks] pointing core.hooksPath at .githooks/"
    @git config core.hooksPath .githooks
    @if [ -f .githooks/pre-commit ]; then chmod +x .githooks/pre-commit || true; fi
    @echo "[install-hooks] done. Verify with: git config --get core.hooksPath"

# ── Three-mode core ──────────────────────────────────────────

# Deterministic: meta-prompter only, dry-run. Writes .soup/plans/<ts>.json.
# No subagent execution. Use to inspect decomposition before committing.
plan goal="":
    @if [ -z "{{goal}}" ]; then echo "usage: just plan \"<goal>\"" >&2; exit 2; fi
    @python -m orchestrator.cli plan "{{goal}}" --dry-run

# Supervised: plan + orchestrator.run + auto-verify. Stop-hook QA gate applies.
# Default path for most work.
go goal="":
    @if [ -z "{{goal}}" ]; then echo "usage: just go \"<goal>\"" >&2; exit 2; fi
    @python -m orchestrator.cli go "{{goal}}"

# Interactive: plan + HITL at each wave boundary. Prompts via ask-user-question.
# Use when goal is fuzzy or the plan is high-risk.
go-i goal="":
    @if [ -z "{{goal}}" ]; then echo "usage: just go-i \"<goal>\"" >&2; exit 2; fi
    @python -m orchestrator.cli go "{{goal}}" --interactive

# Pass-through to /quick command for single-file, no-plan changes.
quick ask="":
    @if [ -z "{{ask}}" ]; then echo "usage: just quick \"<ask>\"" >&2; exit 2; fi
    @python -m orchestrator.cli quick "{{ask}}"

# ── RAG ──────────────────────────────────────────────────────

# Query org knowledge. Returns hits + cited spans.
# Note: wraps `python -m rag.search --query "<q>"`; the CLI expects the
# --query flag (iter-2 dogfood C3 fix).
rag query="":
    @if [ -z "{{query}}" ]; then \
        echo "usage: just rag \"<query>\""; \
        echo "  e.g. just rag \"how does AuthService validate JWTs?\""; \
        exit 2; \
    fi
    @python -m rag.search --query "{{query}}"

# Add source (github://org/repo[@branch], ado://org/project[/wiki],
# ado-wi://org/project/<id|wiql>, file:///path, https://...).
# Wraps `python -m rag.ingest --source "<uri>"`.
rag-ingest source="":
    @if [ -z "{{source}}" ]; then \
        echo "usage: just rag-ingest \"<source-uri>\""; \
        echo "  e.g. just rag-ingest \"github://streck/auth-service\""; \
        echo "       just rag-ingest \"ado://streck/Security\""; \
        echo "       just rag-ingest \"ado-wi://streck/Platform/482\""; \
        exit 2; \
    fi
    @python -m rag.ingest --source "{{source}}"

# Start MCP server so Claude Desktop / other clients can query RAG.
rag-mcp:
    @python -m rag.mcp_server

# Reindex everything already ingested (idempotent).
rag-reindex:
    @python -m rag.ingest --reindex-all

# Quick health check: Postgres reachable? OPENAI_API_KEY set?
# lightrag-hku importable? Exits non-zero on any missing piece so
# operators can wire this into CI / pre-flight scripts.
rag-health:
    @python -m rag.health

# Hydrate a plan's context_excerpts from a researcher findings report.
# Parses the findings table (file|line|relevance|excerpt) and writes a
# plan-hydrated.json. Unmatched findings land in the plan's `notes`.
hydrate-plan findings="" plan="":
    @if [ -z "{{findings}}" ] || [ -z "{{plan}}" ]; then \
        echo "usage: just hydrate-plan <findings.md> <plan.json>"; \
        echo "  e.g. just hydrate-plan .soup/research/my-feature-findings.md .soup/plans/my-feature.json"; \
        exit 2; \
    fi
    @python -m scripts.hydrate_context_excerpts --findings "{{findings}}" --plan "{{plan}}"

# ── QA / verification ────────────────────────────────────────

# Run qa-orchestrator on HEAD (no side effects outside logging).
verify:
    @python -m orchestrator.cli verify --ref HEAD

# Replay the QA gate against a specific run dir.
verify-run run="":
    @if [ -z "{{run}}" ]; then echo "usage: just verify-run <run-id>" >&2; exit 2; fi
    @python -m orchestrator.cli verify --run .soup/runs/{{run}}

# Framework self-tests. Pytest-quiet.
test:
    @pytest -q

# Alias.
test-self: test

# Lint only (ruff). Runs the same command CI uses.
lint:
    @ruff check .

# Typecheck only (mypy strict). Runs the same command CI uses.
typecheck:
    @mypy .

# Full local CI — mirrors .github/workflows/ci.yml so engineers can
# reproduce failures before pushing.
ci: lint typecheck test
    @echo "[ci] all green"

# Format (ruff; non-destructive check first, then apply).
fmt:
    @ruff format .

# Validate a plan JSON against the schema + library roster.
# Wraps `python -m orchestrator.cli plan-validate` per /tasks.md:23.
plan-validate path="":
    @if [ -z "{{path}}" ]; then echo "usage: just plan-validate <path>" >&2; exit 2; fi
    @python -m orchestrator.cli plan-validate "{{path}}"

# Brownfield onboarding: convert prose agent/plan/handoff files into
# ExecutionPlan JSON skeletons under .soup/ingested/<slug>.plan.json.
# ALWAYS review the output and fill `TODO:` markers before running.
# See .claude/commands/ingest-plans.md.
ingest-plans glob="":
    @if [ -z "{{glob}}" ]; then echo "usage: just ingest-plans \"<glob>\"  (e.g. 'AGENT_*_SPEC.md')" >&2; exit 2; fi
    @python -m orchestrator.cli ingest-plans "{{glob}}"

# ── Scaffolding ──────────────────────────────────────────────

# List stack templates.
templates:
    @ls -1 templates/ 2>/dev/null | grep -v '^$' || echo "(no templates yet)"

# Scaffold a new internal app: `just new python-fastapi-postgres my-service`.
new template name:
    @if [ ! -d "templates/{{template}}" ]; then \
        echo "unknown template: {{template}}" >&2; \
        echo "available:"; just templates; exit 2; \
    fi
    @python -m orchestrator.cli new "{{template}}" "{{name}}"

# Create a worktree under .soup/worktrees/<name> for isolated feature work.
worktree name:
    @python -m orchestrator.cli worktree "{{name}}"

# Remove a worktree cleanly.
worktree-rm name:
    @python -m orchestrator.cli worktree --remove "{{name}}"

# ── Permission presets ───────────────────────────────────────

# Copy a named preset from .claude/settings.presets/ over .claude/settings.local.json.
# Prompts for confirmation before overwriting.
# Available presets: `restricted` (minimal, script-style repos) and
# `development` (default soup allow-list snapshot).
# See docs/PATTERNS.md §"Permission presets".
preset name="":
    @if [ -z "{{name}}" ]; then \
        echo "usage: just preset <name>" >&2; \
        echo "available presets:" >&2; \
        ls -1 .claude/settings.presets/ 2>/dev/null | sed 's/\.json$//' | sed 's/^/  - /' >&2; \
        exit 2; \
    fi
    @src=".claude/settings.presets/{{name}}.json"; \
     dst=".claude/settings.local.json"; \
     if [ ! -f "$src" ]; then \
        echo "unknown preset: {{name}}" >&2; \
        echo "available:" >&2; \
        ls -1 .claude/settings.presets/ 2>/dev/null | sed 's/\.json$//' | sed 's/^/  - /' >&2; \
        exit 2; \
     fi; \
     if [ -f "$dst" ]; then \
        echo "overwrite $dst with preset '{{name}}'? (y/N)"; \
        read -r reply; \
        case "$reply" in \
            [yY]|[yY][eE][sS]) ;; \
            *) echo "aborted"; exit 1 ;; \
        esac; \
     fi; \
     cp "$src" "$dst"; \
     echo "preset '{{name}}' copied to $dst"; \
     echo "restart Claude Code to pick up the new permissions."

# ── Observability ────────────────────────────────────────────

# Tail the most recent session JSONL.
logs:
    @python -m orchestrator.cli logs --tail

# Open the experiments table (autoresearch-style append-only metrics).
experiments:
    @python -m orchestrator.cli logs --experiments

# Show the last-run QA report as pretty JSON.
last-qa:
    @python -m orchestrator.cli logs --last-qa

# Reconstruct the parent→child subagent tree for a given run_id.
logs-tree run_id="":
    @if [ -z "{{run_id}}" ]; then echo "usage: just logs-tree <run-id>"; exit 2; fi
    @python -m orchestrator.cli logs tree {{run_id}}

# Grep structured JSONL session logs. Optional --session / --agent filters via soup CLI.
logs-search query="":
    @if [ -z "{{query}}" ]; then echo "usage: just logs-search '<query>'"; exit 2; fi
    @python -m orchestrator.cli logs search "{{query}}"

# Cumulative cost from experiments.tsv (group-by agent|plan|model; since/until optional).
cost-report group_by="agent":
    @python -m orchestrator.cli cost-report --group-by {{group_by}}

# ── Docs ─────────────────────────────────────────────────────

# List docs/ tree. (No toolchain dependency — keeps it portable.)
docs:
    @ls -1R docs/ 2>/dev/null

# Render DESIGN.md to ANSI in terminal (glow/bat if available).
docs-view doc="DESIGN.md":
    @if command -v glow >/dev/null 2>&1; then glow docs/{{doc}}; \
     elif command -v bat >/dev/null 2>&1; then bat docs/{{doc}}; \
     else cat docs/{{doc}}; fi

# ── Housekeeping ─────────────────────────────────────────────

# Remove .soup/runs older than 30 days. Plans + memory are preserved.
clean:
    @python -m orchestrator.cli clean --older-than 30d

# Nuke all caches (keep .env, .soup/memory). Use before a clean reinstall.
# Cross-platform: uses python's shutil.rmtree so it runs identically under
# Git Bash on Windows, macOS, and Linux (no `rm` on cmd/PowerShell PATH).
clean-all: clean
    @python -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ('.venv', '__pycache__', '.pytest_cache', '.ruff_cache', '.mypy_cache')]"

# Print repo + env health summary for bug reports.
doctor:
    @python -m orchestrator.cli doctor
