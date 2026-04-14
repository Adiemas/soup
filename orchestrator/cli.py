"""``soup`` Typer CLI — entry point declared in pyproject.toml.

Commands mirror the justfile surface one-to-one:

* ``soup plan <goal>`` — meta-prompter dry run, writes plan JSON to stdout
  (or ``--out <path>``).
* ``soup plan-validate <path>`` — validate an ExecutionPlan JSON file against
  ``schemas/execution_plan.py`` + the library roster.
* ``soup run <plan_path>`` — orchestrator executes a validated plan file.
* ``soup go <goal>`` — full supervised pipeline (plan -> run -> verify).
* ``soup go-i <goal>`` — same as ``go`` but with HITL wave-boundary prompts.
* ``soup quick <ask>`` — dispatch the ``/quick`` flow (test-engineer -> implementer).
* ``soup install [--hil]`` — register hooks + verify env.
* ``soup new <template> <name>`` — scaffold a new app from ``templates/``.
* ``soup worktree <name> [--remove]`` — manage ``.soup/worktrees/<name>``.
* ``soup logs [--tail N | --experiments | --last-qa]`` — tail session logs.
* ``soup doctor`` — health check (postgres reachable, anthropic key present,
  git configured).
* ``soup clean [--older-than 30d]`` — prune old ``.soup/runs/``.
* ``soup status`` — summarize the most recent run (or ``--run <id>``).
* ``soup verify`` — delegate to ``qa-orchestrator`` via Claude Code CLI or
  emit instructions for the user to run ``/verify``.
* ``soup ingest <src>`` — add a source to the RAG pipeline.
* ``soup search <q>`` — query the RAG pipeline.
"""
# ruff: noqa: B008  # Typer.Option/Argument in defaults is the canonical Typer pattern.

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from orchestrator.meta_prompter import MetaPrompter, MetaPrompterConfig
from orchestrator.orchestrator import Orchestrator, OrchestratorConfig
from orchestrator.state import RunState
from schemas.execution_plan import ExecutionPlan, ExecutionPlanValidator

app = typer.Typer(
    add_completion=False,
    help="Soup — canonical agentic Claude Code framework CLI.",
    no_args_is_help=True,
)
console = Console()

_RUNS_DIR_DEFAULT = Path(".soup/runs")
_PLANS_DIR_DEFAULT = Path(".soup/plans")
_WORKTREES_DIR_DEFAULT = Path(".soup/worktrees")
_LOG_DIR_DEFAULT = Path("logging/agent-runs")
_EXPERIMENTS_TSV = Path("logging/experiments.tsv")
_INGESTED_DIR_DEFAULT = Path(".soup/ingested")


# ---------------------------------------------------------------------------
# plan / run / status / verify / ingest / search
# ---------------------------------------------------------------------------


@app.command()
def plan(
    goal: str = typer.Argument(..., help="Natural-language goal."),
    out: Path | None = typer.Option(
        None, "--out", "-o", help="Write plan JSON here (default: stdout)."
    ),
    library: Path = typer.Option(
        Path("library.yaml"), "--library", help="Path to library.yaml."
    ),
    constitution: Path = typer.Option(
        Path("CONSTITUTION.md"),
        "--constitution",
        help="Path to CONSTITUTION.md.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help=(
            "Accepted for justfile compatibility; ``plan`` is inherently "
            "dry-run (no subagent execution)."
        ),
    ),
) -> None:
    """Run the meta-prompter and emit an ExecutionPlan JSON."""
    _ = dry_run  # always dry-run; flag kept for CLI-surface parity
    config = MetaPrompterConfig(
        library_path=library, constitution_path=constitution
    )
    mp = MetaPrompter(config)
    plan_obj = asyncio.run(mp.plan_for(goal))
    payload = plan_obj.model_dump_json(indent=2)
    if out is None:
        console.print_json(payload)
    else:
        out.write_text(payload, encoding="utf-8")
        console.print(f"[green]Plan written to[/green] {out}")


@app.command("plan-validate")
def plan_validate(
    plan_path: Path = typer.Argument(
        ..., exists=True, readable=True, help="Path to ExecutionPlan JSON."
    ),
    library: Path = typer.Option(
        Path("library.yaml"), "--library", help="Path to library.yaml."
    ),
) -> None:
    """Validate an ExecutionPlan JSON against the schema + library roster.

    Runs :meth:`ExecutionPlan.model_validate` followed by
    :meth:`ExecutionPlanValidator.validate`. Prints a friendly pass/fail.
    Exits 0 on pass, 1 on validation failure, 2 on I/O / JSON errors.
    """
    try:
        raw_text = plan_path.read_text(encoding="utf-8")
    except OSError as exc:
        console.print(f"[red]cannot read[/red] {plan_path}: {exc}")
        raise typer.Exit(code=2) from exc
    try:
        raw = json.loads(raw_text)
    except ValueError as exc:
        console.print(f"[red]invalid JSON[/red] {plan_path}: {exc}")
        raise typer.Exit(code=2) from exc
    try:
        plan_obj = ExecutionPlan.model_validate(raw)
    except Exception as exc:  # pydantic ValidationError, etc.
        console.print(f"[red]schema validation failed[/red]")
        console.print(str(exc))
        raise typer.Exit(code=1) from exc
    try:
        ExecutionPlanValidator.from_library(library).validate(plan_obj)
    except Exception as exc:
        console.print(f"[red]library / DAG validation failed[/red]")
        console.print(str(exc))
        raise typer.Exit(code=1) from exc

    n_steps = len(plan_obj.steps)
    agents = sorted({s.agent for s in plan_obj.steps})
    console.print(f"[green]plan OK[/green] {plan_path}")
    console.print(
        f"  goal:   {plan_obj.goal}\n"
        f"  steps:  {n_steps}\n"
        f"  agents: {', '.join(agents)}"
    )


@app.command("ingest-plans")
def ingest_plans(
    glob: str = typer.Argument(
        ...,
        help=(
            "Glob of brownfield prose files (e.g. 'AGENT_*_SPEC.md', "
            "'*_PLAN.md', '*_HANDOFF.md'). Matched relative to cwd."
        ),
    ),
    library: Path = typer.Option(
        Path("library.yaml"), "--library", help="Path to library.yaml."
    ),
    constitution: Path = typer.Option(
        Path("CONSTITUTION.md"),
        "--constitution",
        help="Path to CONSTITUTION.md.",
    ),
    out_dir: Path = typer.Option(
        _INGESTED_DIR_DEFAULT,
        "--out-dir",
        help="Directory for <source-slug>.plan.json outputs.",
    ),
    fail_fast: bool = typer.Option(
        False,
        "--fail-fast",
        help="Exit non-zero on the first ingestion failure.",
    ),
) -> None:
    """Convert brownfield prose docs to ExecutionPlan skeletons.

    For each file matching *glob*, the meta-prompter runs in ingest mode:
    it extracts work items already described in the prose, emits a
    skeleton ExecutionPlan JSON with ``TODO:`` markers where fields cannot
    be inferred, and writes it to ``<out_dir>/<source-slug>.plan.json``.

    The output is **always a human-review artifact**. Never hand the
    generated JSON straight to ``soup run`` — open each file, fill the
    TODOs, then validate with ``soup plan-validate`` before executing.
    """
    files = sorted(Path(".").glob(glob))
    if not files:
        console.print(f"[yellow]no files matched glob {glob!r}[/yellow]")
        raise typer.Exit(code=0)

    out_dir.mkdir(parents=True, exist_ok=True)
    mp = MetaPrompter(
        MetaPrompterConfig(
            library_path=library, constitution_path=constitution
        )
    )
    validator = ExecutionPlanValidator.from_library(library)

    rows: list[tuple[str, str, str]] = []  # (input, steps, notes)
    any_failed = False
    for src in files:
        try:
            prose = src.read_text(encoding="utf-8")
        except OSError as exc:
            any_failed = True
            rows.append((str(src), "-", f"read error: {exc}"))
            if fail_fast:
                break
            continue

        try:
            plan_obj = asyncio.run(mp.ingest_prose(src, prose))
        except Exception as exc:
            any_failed = True
            rows.append(
                (str(src), "-", f"meta-prompter: {type(exc).__name__}")
            )
            if fail_fast:
                break
            continue

        # Structural validation (roster, deps, cycles, excerpt paths).
        try:
            validator.validate(plan_obj)
            status_note = _describe_unresolved(plan_obj)
        except ValueError as exc:
            # Skeleton with unfilled paths is expected — surface as a
            # note, not a hard failure, so the human can tidy them up.
            status_note = f"validation note: {exc}"

        slug = _slugify(src.stem)
        out_path = out_dir / f"{slug}.plan.json"
        out_path.write_text(
            plan_obj.model_dump_json(indent=2), encoding="utf-8"
        )
        rows.append((str(src), str(len(plan_obj.steps)), status_note))

    table = Table(title="soup ingest-plans")
    table.add_column("input")
    table.add_column("steps extracted", justify="right")
    table.add_column("unresolved fields / notes")
    for n, s, d in rows:
        table.add_row(n, s, d)
    console.print(table)
    console.print(
        f"[dim]outputs:[/dim] {out_dir} "
        "- review each file, resolve `TODO:` markers, then `soup plan-validate`."
    )
    if any_failed and fail_fast:
        raise typer.Exit(code=1)


def _describe_unresolved(plan_obj: ExecutionPlan) -> str:
    """Count ``TODO:`` markers + empty required fields in a skeleton plan."""
    todo_steps = sum(1 for s in plan_obj.steps if "TODO:" in s.prompt)
    empty_scopes = sum(1 for s in plan_obj.steps if not s.files_allowed)
    default_verify = sum(
        1 for s in plan_obj.steps if s.verify_cmd.strip() == "true"
    )
    parts: list[str] = []
    if todo_steps:
        parts.append(f"{todo_steps} step(s) with TODO")
    if empty_scopes:
        parts.append(f"{empty_scopes} with empty files_allowed")
    if default_verify:
        parts.append(f"{default_verify} with default verify_cmd")
    return ", ".join(parts) if parts else "ok"


@app.command()
def run(
    plan_path: Path = typer.Argument(
        ..., exists=True, readable=True, help="Path to plan JSON."
    ),
    library: Path = typer.Option(
        Path("library.yaml"),
        "--library",
        help="Path to library.yaml (for validation).",
    ),
    runs_dir: Path = typer.Option(
        _RUNS_DIR_DEFAULT, "--runs-dir", help="Where to persist run state."
    ),
    no_commit: bool = typer.Option(
        False, "--no-commit", help="Skip git commits on passing steps."
    ),
) -> None:
    """Execute a validated ExecutionPlan via the orchestrator."""
    raw = json.loads(plan_path.read_text(encoding="utf-8"))
    plan_obj = ExecutionPlan.model_validate(raw)
    ExecutionPlanValidator.from_library(library).validate(plan_obj)
    cfg = OrchestratorConfig(
        runs_dir=runs_dir, enable_git_commits=not no_commit
    )
    orch = Orchestrator(cfg)
    result = asyncio.run(orch.run(plan_obj))
    console.print(
        f"[bold]Run {result.run_id}[/bold] "
        f"status=[cyan]{result.status}[/cyan] "
        f"duration={result.duration_sec:.1f}s"
    )
    if result.aborted_reason:
        console.print(f"[red]aborted:[/red] {result.aborted_reason}")
    if result.status != "passed":
        raise typer.Exit(code=1)


@app.command()
def status(
    runs_dir: Path = typer.Option(
        _RUNS_DIR_DEFAULT, "--runs-dir", help="Where run state lives."
    ),
    run_id: str | None = typer.Option(
        None, "--run", help="Specific run id (default: latest)."
    ),
) -> None:
    """Show the most recent run summary (or the one identified by ``--run``)."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(runs_dir.glob("*.json"))
    if not files:
        console.print("[yellow]No runs recorded.[/yellow]")
        return
    path = files[-1]
    if run_id is not None:
        candidate = runs_dir / f"{run_id}.json"
        if not candidate.exists():
            raise typer.BadParameter(f"unknown run id {run_id}")
        path = candidate
    state = RunState.load(path)
    table = Table(title=f"Run {state.run_id}  —  {state.status}")
    table.add_column("step")
    table.add_column("agent")
    table.add_column("wave", justify="right")
    table.add_column("status")
    table.add_column("ms", justify="right")
    for sid, rec in sorted(state.steps.items()):
        table.add_row(
            sid, rec.agent, str(rec.wave), rec.status, str(rec.duration_ms)
        )
    console.print(table)


@app.command()
def verify(
    ref: str = typer.Option(
        "HEAD", "--ref", help="Git ref to scope the QA gate against."
    ),
    run_dir: Path | None = typer.Option(
        None, "--run", help="Replay QA against a specific ``.soup/runs/<id>``."
    ),
) -> None:
    """Run the QA gate via the ``qa-orchestrator`` subagent.

    Tries to shell out to the ``claude`` CLI (``claude -p /verify``) so the
    Stop-hook QA contract is honored end-to-end. If ``claude`` is not on
    PATH, emits clear instructions for the user to run ``/verify``
    interactively.
    """
    claude = shutil.which("claude")
    if claude is None:
        console.print(
            "[yellow]`claude` CLI not found on PATH.[/yellow]\n"
            "Open a Claude Code session in this repo and run [bold]/verify[/bold] "
            "to trigger `qa-orchestrator`.\n"
            f"Reference: ref={ref}"
            + (f", run={run_dir}" if run_dir else "")
        )
        raise typer.Exit(code=2)

    # Build the slash-command invocation. Claude Code accepts /verify in
    # non-interactive mode via `-p`.
    args: list[str] = [claude, "-p", "/verify"]
    if run_dir is not None:
        args[-1] = f"/verify --run {run_dir}"
    console.print(f"[cyan]invoking[/cyan] {' '.join(args)}")
    try:
        completed = subprocess.run(args, check=False)
    except OSError as exc:
        console.print(f"[red]verify error:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    raise typer.Exit(code=completed.returncode)


@app.command()
def ingest(
    src: str = typer.Argument(
        ..., help="Source URI: github://repo, ado://wiki, file://path, https://..."
    ),
    tags: str | None = typer.Option(
        None, "--tags", help="Comma-separated metadata tags."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Iterate chunks without writing to backend."
    ),
) -> None:
    """Ingest a source into the RAG pipeline."""
    rag_pkg = _load_rag_or_exit()
    entry = _resolve_rag_callable(rag_pkg, ("ingest", "ingest_source"))
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    try:
        result = entry(src, dry_run=dry_run, tags=tag_list)
    except TypeError:
        # Older entry point with a bare (uri) signature.
        result = entry(src)
    console.print(f"[green]ingested[/green] {src}")
    if hasattr(result, "summary"):
        console.print(result.summary())


@app.command()
def search(
    query: str = typer.Argument(..., help="Natural-language query."),
    mode: str = typer.Option(
        "hybrid", "--mode", help="hybrid | vector | graph"
    ),
    top_k: int = typer.Option(8, "--top-k", help="Max hits."),
) -> None:
    """Query the RAG pipeline."""
    rag_pkg = _load_rag_or_exit()
    entry = _resolve_rag_callable(rag_pkg, ("search", "query"))
    try:
        hits = entry(query, mode=mode, top_k=top_k)
    except TypeError:
        hits = entry(query)
    for hit in hits:
        console.print(hit)


# ---------------------------------------------------------------------------
# go / go-i / quick — full pipelines
# ---------------------------------------------------------------------------


@app.command()
def go(
    goal: str = typer.Argument(..., help="Natural-language goal."),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        "-i",
        help="Prompt at each wave boundary (HITL mode).",
    ),
    library: Path = typer.Option(Path("library.yaml"), "--library"),
    constitution: Path = typer.Option(Path("CONSTITUTION.md"), "--constitution"),
    runs_dir: Path = typer.Option(_RUNS_DIR_DEFAULT, "--runs-dir"),
    plans_dir: Path = typer.Option(_PLANS_DIR_DEFAULT, "--plans-dir"),
    no_commit: bool = typer.Option(False, "--no-commit"),
) -> None:
    """Supervised pipeline: plan -> run -> verify.

    In interactive mode (``--interactive`` / invoked by ``soup go-i``),
    asks the user to confirm before each wave boundary.
    """
    mp = MetaPrompter(
        MetaPrompterConfig(
            library_path=library, constitution_path=constitution
        )
    )
    console.print(f"[bold]planning:[/bold] {goal}")
    plan_obj = asyncio.run(mp.plan_for(goal))
    plans_dir.mkdir(parents=True, exist_ok=True)
    slug = _slugify(plan_obj.goal)
    plan_path = plans_dir / f"{slug}.json"
    plan_path.write_text(plan_obj.model_dump_json(indent=2), encoding="utf-8")
    console.print(f"[green]plan written:[/green] {plan_path}")

    ExecutionPlanValidator.from_library(library).validate(plan_obj)

    if interactive:
        if not typer.confirm(
            f"plan has {len(plan_obj.steps)} steps; proceed?", default=True
        ):
            console.print("[yellow]aborted by user[/yellow]")
            raise typer.Exit(code=0)

    cfg = OrchestratorConfig(
        runs_dir=runs_dir, enable_git_commits=not no_commit
    )
    orch = Orchestrator(cfg)
    # HITL: monkey-patch _run_wave to prompt before each wave.
    if interactive:
        _install_hitl_prompts(orch)

    result = asyncio.run(orch.run(plan_obj))
    console.print(
        f"[bold]Run {result.run_id}[/bold] "
        f"status=[cyan]{result.status}[/cyan] "
        f"duration={result.duration_sec:.1f}s"
    )
    if result.aborted_reason:
        console.print(f"[red]aborted:[/red] {result.aborted_reason}")
    if result.status != "passed":
        raise typer.Exit(code=1)

    console.print("[cyan]invoking QA gate (soup verify)...[/cyan]")
    claude = shutil.which("claude")
    if claude is None:
        console.print(
            "[yellow]`claude` CLI not on PATH — run /verify manually to "
            "close the QA gate.[/yellow]"
        )
    else:
        subprocess.run([claude, "-p", "/verify"], check=False)


@app.command("go-i")
def go_i(
    goal: str = typer.Argument(..., help="Natural-language goal."),
    library: Path = typer.Option(Path("library.yaml"), "--library"),
    constitution: Path = typer.Option(Path("CONSTITUTION.md"), "--constitution"),
    runs_dir: Path = typer.Option(_RUNS_DIR_DEFAULT, "--runs-dir"),
    plans_dir: Path = typer.Option(_PLANS_DIR_DEFAULT, "--plans-dir"),
    no_commit: bool = typer.Option(False, "--no-commit"),
) -> None:
    """Interactive (HITL) alias for ``soup go --interactive``."""
    go(
        goal=goal,
        interactive=True,
        library=library,
        constitution=constitution,
        runs_dir=runs_dir,
        plans_dir=plans_dir,
        no_commit=no_commit,
    )


@app.command()
def quick(
    ask: str = typer.Argument(..., help="The one-line change request."),
) -> None:
    """Dispatch the ``/quick`` flow (test-engineer -> implementer via Claude Code).

    Enforces the TDD iron law: spawns a failing test first, then the
    implementation. See ``.claude/commands/quick.md`` for the contract.
    """
    if ask.strip().endswith("--no-test"):
        console.print(
            "[red]rejected:[/red] TDD iron law; use /quick-yolo only for "
            "genuinely untestable trivial changes like typos and formatting."
        )
        raise typer.Exit(code=2)

    claude = shutil.which("claude")
    if claude is None:
        console.print(
            "[yellow]`claude` CLI not on PATH.[/yellow] Open a Claude Code "
            f"session and run:  [bold]/quick {ask}[/bold]"
        )
        raise typer.Exit(code=2)
    args = [claude, "-p", f"/quick {ask}"]
    console.print(f"[cyan]invoking[/cyan] {' '.join(args)}")
    raise typer.Exit(code=subprocess.run(args, check=False).returncode)


# ---------------------------------------------------------------------------
# install / new / worktree / logs / doctor / clean
# ---------------------------------------------------------------------------


@app.command()
def install(
    mode: str = typer.Argument(
        "", help="Optional mode tag; 'hil' prints HITL banner."
    ),
    hil: bool = typer.Option(
        False, "--hil", help="Register hooks in HITL-friendly verbose mode."
    ),
) -> None:
    """Register hooks + verify env.

    Reads ``.claude/settings.json`` to confirm hook wiring is present,
    ensures ``.env`` exists, and writes a setup log agents can read for
    continuity.
    """
    log = Path(".claude/hooks/setup.init.log")
    log.parent.mkdir(parents=True, exist_ok=True)

    settings = Path(".claude/settings.json")
    checks: list[tuple[str, bool, str]] = []
    if not settings.exists():
        console.print(f"[red].claude/settings.json missing[/red]")
        checks.append(("settings.json", False, "missing"))
    else:
        try:
            cfg = json.loads(settings.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            console.print(f"[red]settings.json invalid JSON:[/red] {e}")
            checks.append(("settings.json", False, f"JSON error: {e}"))
            cfg = {}
        else:
            hooks = cfg.get("hooks", {}) or {}
            for event in (
                "SessionStart",
                "UserPromptSubmit",
                "PreToolUse",
                "PostToolUse",
                "SubagentStart",
                "Stop",
            ):
                present = bool(hooks.get(event))
                checks.append((f"hook:{event}", present, "ok" if present else "missing"))

    env = Path(".env")
    env_example = Path(".env.example")
    if not env.exists():
        if env_example.exists():
            shutil.copyfile(env_example, env)
            console.print(f"[green]stubbed[/green] {env}")
            checks.append((".env", True, "stubbed from .env.example"))
        else:
            checks.append((".env", False, "missing and no .env.example"))
    else:
        checks.append((".env", True, "exists"))

    for d in (".soup", ".soup/plans", ".soup/runs", ".soup/memory", ".soup/worktrees"):
        Path(d).mkdir(parents=True, exist_ok=True)
    Path("logging/agent-runs").mkdir(parents=True, exist_ok=True)
    checks.append((".soup tree", True, "ensured"))

    hil_mode = hil or mode.lower() == "hil"
    if hil_mode:
        console.print(
            "[bold cyan]HITL mode:[/bold cyan] "
            "prefer `just go-i` and review wave boundaries."
        )

    # Write the setup log that /install command step 2 reads.
    log.write_text(
        json.dumps(
            {
                "ts": datetime.now(UTC).isoformat(timespec="seconds"),
                "mode": "hil" if hil_mode else "standard",
                "checks": [
                    {"name": n, "ok": ok, "detail": d} for n, ok, d in checks
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    failed = [c for c in checks if not c[1]]
    table = Table(title="soup install")
    table.add_column("check")
    table.add_column("ok")
    table.add_column("detail")
    for n, ok, d in checks:
        table.add_row(n, "[green]yes[/green]" if ok else "[red]no[/red]", d)
    console.print(table)
    console.print(f"[dim]log:[/dim] {log}")
    if failed:
        raise typer.Exit(code=1)


@app.command()
def new(
    template: str = typer.Argument(..., help="Template name under templates/."),
    name: str = typer.Argument(..., help="Target app name."),
    dest: Path = typer.Option(
        Path(".."),
        "--dest",
        help="Parent directory for the new app (default: repo's parent).",
    ),
) -> None:
    """Scaffold a new internal app from ``templates/<template>``."""
    tpl = Path("templates") / template
    if not tpl.is_dir():
        available = sorted(p.name for p in Path("templates").iterdir() if p.is_dir())
        console.print(f"[red]unknown template[/red] {template}")
        console.print(f"available: {', '.join(available) or '(none)'}")
        raise typer.Exit(code=2)
    target = dest / name
    if target.exists():
        console.print(f"[red]target exists:[/red] {target}")
        raise typer.Exit(code=2)
    shutil.copytree(tpl, target)
    console.print(f"[green]scaffolded[/green] {target} from {tpl}")


@app.command()
def worktree(
    name: str = typer.Argument(..., help="Worktree name under .soup/worktrees/."),
    remove: bool = typer.Option(
        False, "--remove", help="Remove the worktree instead of creating it."
    ),
) -> None:
    """Manage isolated git worktrees under ``.soup/worktrees/<name>``."""
    _WORKTREES_DIR_DEFAULT.mkdir(parents=True, exist_ok=True)
    path = _WORKTREES_DIR_DEFAULT / name
    if remove:
        if not path.exists():
            console.print(f"[yellow]no worktree at[/yellow] {path}")
            raise typer.Exit(code=0)
        rc = subprocess.run(
            ["git", "worktree", "remove", str(path)], check=False
        ).returncode
        if rc != 0:
            console.print(
                f"[red]git worktree remove failed[/red] (exit {rc}); "
                f"try `git worktree remove --force {path}` if intentional."
            )
        raise typer.Exit(code=rc)

    if path.exists():
        console.print(f"[yellow]worktree already exists:[/yellow] {path}")
        raise typer.Exit(code=0)
    branch = f"soup/{name}"
    args = ["git", "worktree", "add", "-b", branch, str(path)]
    console.print(f"[cyan]{' '.join(args)}[/cyan]")
    rc = subprocess.run(args, check=False).returncode
    if rc != 0:
        console.print(f"[red]git worktree add failed[/red] (exit {rc})")
    raise typer.Exit(code=rc)


# ---------------------------------------------------------------------------
# logs — subapp with tail / tree / search (iter-3 ε4)
# ---------------------------------------------------------------------------


logs_app = typer.Typer(
    add_completion=False,
    help="Inspect agent-run logs (tail / tree / search).",
    no_args_is_help=False,
    invoke_without_command=True,
)
app.add_typer(logs_app, name="logs")


@logs_app.callback()
def logs_root(
    ctx: typer.Context,
    tail: int = typer.Option(
        50, "--tail", help="Lines to tail from the latest session JSONL."
    ),
    experiments: bool = typer.Option(
        False, "--experiments", help="Print logging/experiments.tsv instead."
    ),
    last_qa: bool = typer.Option(
        False, "--last-qa", help="Print the most recent qa_report.json."
    ),
    log_dir: Path = typer.Option(
        _LOG_DIR_DEFAULT, "--log-dir", help="Directory of session JSONLs."
    ),
) -> None:
    """Tail/inspect logs. With no subcommand, behaves like the legacy CLI.

    Backward-compatible: ``soup logs --experiments``, ``soup logs --last-qa``,
    ``soup logs --tail N`` all still work. New subcommands:

    * ``soup logs tail [--session <id>]``
    * ``soup logs tree <run_id>``
    * ``soup logs search <query> [--session <id>] [--agent <name>]``
    """
    if ctx.invoked_subcommand is not None:
        return

    if experiments:
        tsv = _EXPERIMENTS_TSV
        if not tsv.exists():
            console.print(f"[yellow]{tsv} not found[/yellow]")
            raise typer.Exit(code=0)
        console.print(tsv.read_text(encoding="utf-8"))
        return

    if last_qa:
        candidates = sorted(_RUNS_DIR_DEFAULT.glob("*/qa_report.json"))
        if not candidates:
            console.print("[yellow]no qa_report.json under .soup/runs/[/yellow]")
            raise typer.Exit(code=0)
        latest = candidates[-1]
        console.print(f"[dim]{latest}[/dim]")
        console.print_json(latest.read_text(encoding="utf-8"))
        return

    if not log_dir.exists():
        console.print(f"[yellow]{log_dir} does not exist yet[/yellow]")
        raise typer.Exit(code=0)
    files = sorted(log_dir.glob("session-*.jsonl"))
    if not files:
        console.print(f"[yellow]no session JSONLs under {log_dir}[/yellow]")
        raise typer.Exit(code=0)
    latest = files[-1]
    console.print(f"[dim]{latest}[/dim]")
    lines = latest.read_text(encoding="utf-8").splitlines()
    for line in lines[-tail:]:
        console.print(line)


@logs_app.command("tail")
def logs_tail(
    session: str | None = typer.Option(
        None, "--session", "-s", help="Tail a specific session id (default: latest)."
    ),
    n: int = typer.Option(50, "--n", "-n", help="Lines to tail."),
    log_dir: Path = typer.Option(
        _LOG_DIR_DEFAULT, "--log-dir", help="Directory of session JSONLs."
    ),
) -> None:
    """Tail a session JSONL (latest by default; use ``--session`` to pick)."""
    if not log_dir.exists():
        console.print(f"[yellow]{log_dir} does not exist yet[/yellow]")
        raise typer.Exit(code=0)
    if session:
        path = log_dir / f"session-{session}.jsonl"
        if not path.exists():
            console.print(f"[red]no session JSONL for {session}[/red]")
            raise typer.Exit(code=1)
    else:
        files = sorted(log_dir.glob("session-*.jsonl"))
        if not files:
            console.print(
                f"[yellow]no session JSONLs under {log_dir}[/yellow]"
            )
            raise typer.Exit(code=0)
        path = files[-1]
    console.print(f"[dim]{path}[/dim]")
    for line in path.read_text(encoding="utf-8").splitlines()[-n:]:
        console.print(line)


@logs_app.command("tree")
def logs_tree(
    run_id: str = typer.Argument(..., help="Orchestrator run id to render."),
    log_dir: Path = typer.Option(
        _LOG_DIR_DEFAULT, "--log-dir", help="Directory of session JSONLs."
    ),
) -> None:
    """Reconstruct + print the wave tree for a given orchestrator run.

    Scans every ``session-*.jsonl`` under ``--log-dir`` for entries
    where ``root_run_id == <run_id>``. Builds a parent→children map
    keyed on ``session_id`` and renders it as indented text. Sessions
    with no parent inside the run are roots; cycles (shouldn't happen)
    are broken by visiting each node at most once.
    """
    if not log_dir.exists():
        console.print(f"[yellow]{log_dir} does not exist yet[/yellow]")
        raise typer.Exit(code=0)
    nodes = _load_run_nodes(log_dir, run_id)
    if not nodes:
        console.print(
            f"[yellow]no JSONL entries with root_run_id={run_id}[/yellow]"
        )
        raise typer.Exit(code=0)
    children: dict[str | None, list[str]] = {}
    for sid, info in nodes.items():
        children.setdefault(info["parent"], []).append(sid)
    for kids in children.values():
        kids.sort()
    console.print(f"[bold]Wave tree for run {run_id}[/bold]")
    seen: set[str] = set()

    def _render(parent: str | None, depth: int) -> None:
        for sid in children.get(parent, []):
            if sid in seen:
                continue
            seen.add(sid)
            info = nodes[sid]
            wave = info.get("wave")
            wave_str = f"w{wave}" if wave is not None else "w?"
            agent = info.get("agent") or "?"
            step = info.get("step") or "?"
            indent = "  " * depth
            console.print(
                f"{indent}- [cyan]{sid}[/cyan] {agent} {wave_str} step={step}"
            )
            _render(sid, depth + 1)

    _render(None, 0)


@logs_app.command("search")
def logs_search(
    query: str = typer.Argument(..., help="Regex to grep against each JSONL line."),
    session: str | None = typer.Option(
        None, "--session", help="Restrict to a single session id."
    ),
    agent: str | None = typer.Option(
        None, "--agent", help="Restrict to entries from this agent role."
    ),
    log_dir: Path = typer.Option(
        _LOG_DIR_DEFAULT, "--log-dir", help="Directory of session JSONLs."
    ),
) -> None:
    """Grep structured JSONL logs for matching entries.

    Uses Python ``re.search`` so call-site flags are not required.
    Filters apply *before* the regex match, narrowing the scan.
    """
    if not log_dir.exists():
        console.print(f"[yellow]{log_dir} does not exist yet[/yellow]")
        raise typer.Exit(code=0)
    try:
        pat = re.compile(query)
    except re.error as exc:
        console.print(f"[red]invalid regex: {exc}[/red]")
        raise typer.Exit(code=2) from exc
    if session:
        files = [log_dir / f"session-{session}.jsonl"]
    else:
        files = sorted(log_dir.glob("session-*.jsonl"))
    n = 0
    for path in files:
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            if agent:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("agent") != agent:
                    continue
            if pat.search(line):
                console.print(f"[dim]{path.name}[/dim] {line}")
                n += 1
    console.print(f"[dim]({n} matches)[/dim]")


# ---------------------------------------------------------------------------
# cost-report — aggregate experiments.tsv (iter-3 ε4)
# ---------------------------------------------------------------------------


@app.command("cost-report")
def cost_report(
    since: str | None = typer.Option(
        None, "--since", help="Lower bound on ts (ISO date, e.g. 2026-04-01)."
    ),
    until: str | None = typer.Option(
        None, "--until", help="Upper bound on ts (ISO date, e.g. 2026-04-30)."
    ),
    group_by: str = typer.Option(
        "model",
        "--group-by",
        help="Aggregation key: ``agent`` | ``plan`` | ``model`` | ``run``.",
    ),
    experiments_tsv: Path = typer.Option(
        _EXPERIMENTS_TSV,
        "--experiments-tsv",
        help="Path to logging/experiments.tsv.",
    ),
) -> None:
    """Aggregate ``cost_usd`` from ``experiments.tsv`` and print a table.

    The TSV carries a row per ExecutionPlan run (post-ε2 split). We bucket
    by the requested key, sum ``cost_usd`` (stripping the ``~`` estimate
    prefix), and order rows by descending cost. ``--group-by plan`` keys
    on the truncated goal column. ``--group-by model`` is a placeholder
    that always returns the single bucket "all" today (per-model split
    requires per-step data; ε5).
    """
    if not experiments_tsv.exists():
        console.print(f"[yellow]{experiments_tsv} not found[/yellow]")
        raise typer.Exit(code=0)
    rows = _read_experiments_tsv(experiments_tsv)
    if since:
        rows = [r for r in rows if r.get("ts", "") >= since]
    if until:
        rows = [r for r in rows if r.get("ts", "") <= until + "T99"]
    buckets = _aggregate_cost(rows, group_by)
    if not buckets:
        console.print("[yellow]no rows after filtering[/yellow]")
        return
    table = Table(title=f"cost-report (group_by={group_by})")
    table.add_column("bucket")
    table.add_column("runs", justify="right")
    table.add_column("cost_usd", justify="right")
    total = 0.0
    for bucket, (n, cost) in sorted(
        buckets.items(), key=lambda kv: -kv[1][1]
    ):
        table.add_row(bucket, str(n), f"~{cost:.4f}")
        total += cost
    console.print(table)
    console.print(f"[dim]total: ~${total:.4f} across {len(rows)} run(s)[/dim]")


def _load_run_nodes(log_dir: Path, run_id: str) -> dict[str, dict[str, Any]]:
    """Return ``{session_id: {parent, agent, wave, step}}`` for *run_id*.

    Each session contributes the first non-empty value seen for parent /
    agent / wave / step across its JSONL lines (Spawn-marker entries
    typically carry the full set; later entries may be sparse).
    """
    nodes: dict[str, dict[str, Any]] = {}
    for path in sorted(log_dir.glob("session-*.jsonl")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("root_run_id") != run_id:
                continue
            sid = rec.get("session_id")
            if not isinstance(sid, str):
                continue
            slot = nodes.setdefault(
                sid,
                {"parent": None, "agent": None, "wave": None, "step": None},
            )
            if slot["parent"] is None and rec.get("parent_session_id"):
                slot["parent"] = rec["parent_session_id"]
            if slot["agent"] is None and rec.get("agent"):
                slot["agent"] = rec["agent"]
            if slot["wave"] is None and rec.get("wave_idx") is not None:
                slot["wave"] = rec["wave_idx"]
            if slot["step"] is None and rec.get("step_id"):
                slot["step"] = rec["step_id"]
    return nodes


def _read_experiments_tsv(path: Path) -> list[dict[str, str]]:
    """Parse experiments.tsv (post-ε2 split) into row-dicts.

    Skips ``# soup-schema:`` comment lines and the header row; every
    surviving line must have the same column count as the header.
    """
    rows: list[dict[str, str]] = []
    text = path.read_text(encoding="utf-8")
    header: list[str] | None = None
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cols = line.split("\t")
        if header is None:
            header = cols
            continue
        if len(cols) != len(header):
            continue  # ignore malformed (legacy mixed-shape) rows
        rows.append(dict(zip(header, cols, strict=False)))
    return rows


def _aggregate_cost(
    rows: list[dict[str, str]], group_by: str
) -> dict[str, tuple[int, float]]:
    """Aggregate a row list into ``{bucket: (n_rows, total_cost_usd)}``.

    Cost values are stripped of the leading ``~`` estimate prefix and
    parsed as floats. Bad values are skipped (counted under their bucket
    but not added to the total).
    """
    out: dict[str, tuple[int, float]] = {}
    for row in rows:
        if group_by == "agent":
            bucket = "all"  # per-agent rollup needs per-step data (ε5)
        elif group_by == "plan":
            bucket = (row.get("goal") or "<unknown>")[:60]
        elif group_by == "run":
            bucket = row.get("run_id", "<unknown>")
        else:
            bucket = "all"  # default model bucket; per-model needs ε5
        raw = row.get("cost_usd", "0").lstrip("~").strip()
        try:
            cost = float(raw)
        except ValueError:
            cost = 0.0
        n, prev = out.get(bucket, (0, 0.0))
        out[bucket] = (n + 1, prev + cost)
    return out


@app.command()
def doctor() -> None:
    """Print repo + env health summary for bug reports."""
    rows: list[tuple[str, str, str]] = []

    # Python / venv
    rows.append(("python", "ok", sys.version.split()[0]))
    rows.append(("platform", "ok", sys.platform))

    # git
    git = shutil.which("git")
    rows.append(("git", "ok" if git else "missing", git or "-"))
    if git:
        try:
            name = subprocess.run(
                [git, "config", "user.name"], capture_output=True, text=True
            ).stdout.strip()
            email = subprocess.run(
                [git, "config", "user.email"], capture_output=True, text=True
            ).stdout.strip()
            rows.append(
                (
                    "git user",
                    "ok" if name and email else "warn",
                    f"{name} <{email}>" if name else "(not configured)",
                )
            )
        except OSError as e:
            rows.append(("git user", "err", repr(e)))

        # Verify core.hooksPath points at our managed hooks dir so the
        # secret scanner (Constitution Art. VI.3) runs at commit time.
        try:
            hooks_path = subprocess.run(
                [git, "config", "--get", "core.hooksPath"],
                capture_output=True,
                text=True,
            ).stdout.strip()
            if hooks_path.replace("\\", "/").rstrip("/") == ".githooks":
                rows.append(("git hooksPath", "ok", hooks_path))
            elif hooks_path:
                rows.append(
                    (
                        "git hooksPath",
                        "warn",
                        f"{hooks_path} (expected .githooks — run `just install-hooks`)",
                    )
                )
            else:
                rows.append(
                    (
                        "git hooksPath",
                        "warn",
                        "(unset — run `just install-hooks` to enable the secret scanner)",
                    )
                )
        except OSError as e:
            rows.append(("git hooksPath", "err", repr(e)))

    # Anthropic key
    key = os.environ.get("ANTHROPIC_API_KEY")
    rows.append(
        (
            "ANTHROPIC_API_KEY",
            "ok" if key else "missing",
            f"{key[:8]}..." if key else "(set it in .env)",
        )
    )

    # claude CLI
    claude = shutil.which("claude")
    rows.append(("claude CLI", "ok" if claude else "missing", claude or "-"))

    # postgres
    pg_url = os.environ.get("POSTGRES_URL") or os.environ.get("DATABASE_URL")
    rows.append(
        (
            "POSTGRES_URL",
            "ok" if pg_url else "missing",
            _redact_pg_url(pg_url) if pg_url else "(set for RAG backend)",
        )
    )
    if pg_url:
        psql = shutil.which("psql")
        if psql:
            try:
                rc = subprocess.run(
                    [psql, pg_url, "-c", "SELECT 1;"],
                    capture_output=True,
                    timeout=5,
                    check=False,
                ).returncode
                rows.append(
                    ("postgres reach", "ok" if rc == 0 else "err", f"psql exit {rc}")
                )
            except (OSError, subprocess.TimeoutExpired) as e:
                rows.append(("postgres reach", "err", repr(e)))
        else:
            rows.append(("postgres reach", "skip", "psql not on PATH"))

    # docker
    docker = shutil.which("docker")
    rows.append(("docker", "ok" if docker else "missing", docker or "-"))

    # library.yaml + CONSTITUTION.md
    rows.append(
        (
            "library.yaml",
            "ok" if Path("library.yaml").exists() else "missing",
            str(Path("library.yaml").resolve()),
        )
    )
    rows.append(
        (
            "CONSTITUTION.md",
            "ok" if Path("CONSTITUTION.md").exists() else "missing",
            str(Path("CONSTITUTION.md").resolve()),
        )
    )

    table = Table(title="soup doctor")
    table.add_column("check")
    table.add_column("status")
    table.add_column("detail")
    for n, s, d in rows:
        color = {"ok": "green", "missing": "red", "err": "red", "warn": "yellow"}.get(
            s, "dim"
        )
        table.add_row(n, f"[{color}]{s}[/{color}]", d)
    console.print(table)
    # Exit non-zero if anything is missing/err so scripts can key off it.
    bad = [r for r in rows if r[1] in ("missing", "err")]
    if bad:
        raise typer.Exit(code=1)


@app.command()
def clean(
    older_than: str = typer.Option(
        "30d",
        "--older-than",
        help="Prune .soup/runs/ older than this duration (e.g. 30d, 7d, 24h).",
    ),
    caches: bool = typer.Option(
        False,
        "--caches",
        help="Also remove .venv, __pycache__, .pytest_cache, .ruff_cache, .mypy_cache.",
    ),
    runs_dir: Path = typer.Option(
        _RUNS_DIR_DEFAULT, "--runs-dir", help="Runs directory to prune."
    ),
) -> None:
    """Prune old ``.soup/runs/`` entries (and optionally Python caches)."""
    cutoff = _parse_duration(older_than)
    now = time.time()
    removed: list[Path] = []
    if runs_dir.exists():
        for child in runs_dir.iterdir():
            try:
                mtime = child.stat().st_mtime
            except OSError:
                continue
            if now - mtime > cutoff:
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    try:
                        child.unlink()
                    except OSError:
                        continue
                removed.append(child)
    console.print(f"[green]pruned[/green] {len(removed)} entries older than {older_than}")

    if caches:
        for path in (
            Path(".venv"),
            Path(".pytest_cache"),
            Path(".ruff_cache"),
            Path(".mypy_cache"),
        ):
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
                console.print(f"[dim]rm[/dim] {path}")
        # __pycache__ is recursive
        for pyc in Path(".").rglob("__pycache__"):
            shutil.rmtree(pyc, ignore_errors=True)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _slugify(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    s = re.sub(r"[-\s]+", "-", s)
    return s[:40] or "plan"


def _parse_duration(spec: str) -> float:
    """Parse '30d' / '24h' / '10m' / '60s' into seconds."""
    m = re.fullmatch(r"(\d+)([smhd])", spec.strip().lower())
    if not m:
        raise typer.BadParameter(
            f"bad duration {spec!r}; use e.g. 30d, 24h, 10m, 60s"
        )
    n = int(m.group(1))
    unit = m.group(2)
    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    return float(n * mult)


def _redact_pg_url(url: str) -> str:
    return re.sub(r"(://[^:]+:)[^@]+(@)", r"\1***\2", url)


def _install_hitl_prompts(orch: Orchestrator) -> None:
    """Monkey-patch the orchestrator so each wave prompts the user.

    Non-invasive: wraps ``_run_wave`` so interactive flows do not affect
    the production orchestrator codepath.
    """
    original = orch._run_wave  # type: ignore[attr-defined]
    wave_counter: dict[str, int] = {"n": 0}

    async def _wrapped(**kwargs: Any) -> Any:
        wave_counter["n"] += 1
        idx = wave_counter["n"]
        wave = kwargs["wave"]
        console.print(
            f"[bold cyan]HITL wave {idx}[/bold cyan] with "
            f"{len(wave)} step(s): {', '.join(s.id for s in wave)}"
        )
        if not typer.confirm(f"proceed with wave {idx}?", default=True):
            raise typer.Exit(code=0)
        return await original(**kwargs)

    orch._run_wave = _wrapped  # type: ignore[attr-defined]


def _load_rag_or_exit() -> Any:
    """Import ``rag`` or exit with a clear message."""
    try:
        import rag
    except ImportError as e:
        console.print(
            "[yellow]rag package not available. "
            "Ensure `lightrag-hku` is installed.[/yellow]"
        )
        raise typer.Exit(code=2) from e
    return rag


def _resolve_rag_callable(module: Any, candidates: tuple[str, ...]) -> Any:
    """Pick the first attribute on ``module`` from ``candidates`` that is callable.

    ``rag/__init__.py`` re-exports module-level ``search`` and ``ingest``
    sync-bridge functions (see ``rag.search.search`` and
    ``rag.ingest.ingest``). This resolver keeps the door open for
    alternative entry-point names (``ingest_source``, ``query``).
    """
    for name in candidates:
        attr = getattr(module, name, None)
        if callable(attr):
            return attr
    console.print(
        "[red]rag package is missing a callable entry point "
        f"({' / '.join(candidates)}).[/red]"
    )
    raise typer.Exit(code=2)


def main() -> None:  # pragma: no cover — thin wrapper for console script
    """Console-script entry point."""
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
