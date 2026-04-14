"""ado-wrap — agent-callable Azure DevOps wrapper.

Wraps ``az devops``. Credentials come from ``ADO_PAT`` env var;
if unset, the wrapper logs a warning payload and only ``--dry-run`` mode works.

Subcommands:
- work-item-list [--query WIQL]
- work-item-get <id>
- work-item-create <title> <type>
- pr-list
- pr-create
- pipeline-list
- pipeline-run <id>
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import click

from . import emit_error, emit_ok, run_cmd


def _pat_status() -> tuple[bool, str]:
    """Report whether ADO_PAT is set; emit warning log if missing."""
    pat = os.environ.get("ADO_PAT")
    if pat:
        return True, "ok"
    # Soft warning on stderr so stdout remains pure JSON for agents.
    sys.stderr.write(
        "[ado-wrap] WARNING: ADO_PAT not set; use --dry-run or export ADO_PAT\n"
    )
    return False, "ADO_PAT not set"


def _az(args: list[str]) -> tuple[int, str, str]:
    """Invoke ``az`` with args; returns (rc, stdout, stderr)."""
    env = dict(os.environ)
    if env.get("ADO_PAT"):
        env["AZURE_DEVOPS_EXT_PAT"] = env["ADO_PAT"]
    res = run_cmd(["az", *args], env=env, check=False, timeout=300.0)
    return res.returncode, res.stdout, res.stderr


def _dry(argv: list[str], json_mode: bool) -> None:
    """Print what we *would* have run, for stub/preview mode."""
    emit_ok(
        {
            "status": "ok",
            "dry_run": True,
            "would_run": ["az", *argv],
        },
        json_mode=json_mode,
    )


def _json_parse_or_error(stdout: str, stderr: str, rc: int, json_mode: bool) -> Any:
    """Parse az JSON output; emit structured error on failure."""
    if rc != 0:
        emit_error(stderr.strip() or "az command failed", code=rc, json_mode=json_mode)
        return None
    if not stdout.strip():
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        emit_error(f"az returned non-JSON: {e}", code=1, json_mode=json_mode)
        return None


@click.group(name="ado-wrap", help="JSON-first Azure DevOps wrapper for soup agents.")
def cli() -> None:
    """Root command group."""


@cli.command("work-item-list")
@click.option("--query", "wiql", default=None, help="WIQL query (else uses default).")
@click.option("--project", default=None)
@click.option("--organization", default=None)
@click.option("--dry-run", is_flag=True)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def wi_list_cmd(
    wiql: str | None,
    project: str | None,
    organization: str | None,
    dry_run: bool,
    json_mode: bool,
) -> None:
    """List work items (WIQL optional)."""
    q = wiql or "SELECT [System.Id], [System.Title], [System.State] FROM WorkItems"
    args = ["boards", "query", "--wiql", q, "-o", "json"]
    if project:
        args.extend(["--project", project])
    if organization:
        args.extend(["--organization", organization])
    if dry_run:
        _dry(args, json_mode)
        return
    _pat_status()
    rc, out, err = _az(args)
    data = _json_parse_or_error(out, err, rc, json_mode)
    if data is None:
        return
    emit_ok(
        {"status": "ok", "count": len(data) if isinstance(data, list) else 1, "items": data},
        json_mode=json_mode,
    )


@cli.command("work-item-get")
@click.argument("id_", metavar="ID", type=int)
@click.option("--dry-run", is_flag=True)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def wi_get_cmd(id_: int, dry_run: bool, json_mode: bool) -> None:
    """Fetch a single work item."""
    args = ["boards", "work-item", "show", "--id", str(id_), "-o", "json"]
    if dry_run:
        _dry(args, json_mode)
        return
    _pat_status()
    rc, out, err = _az(args)
    data = _json_parse_or_error(out, err, rc, json_mode)
    if data is None:
        return
    emit_ok({"status": "ok", "item": data}, json_mode=json_mode)


@cli.command("work-item-create")
@click.argument("title")
@click.argument("type_", metavar="TYPE")
@click.option("--description", default=None)
@click.option("--project", default=None)
@click.option("--dry-run", is_flag=True)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def wi_create_cmd(
    title: str,
    type_: str,
    description: str | None,
    project: str | None,
    dry_run: bool,
    json_mode: bool,
) -> None:
    """Create a new work item."""
    args = [
        "boards",
        "work-item",
        "create",
        "--title",
        title,
        "--type",
        type_,
        "-o",
        "json",
    ]
    if description:
        args.extend(["--description", description])
    if project:
        args.extend(["--project", project])
    if dry_run:
        _dry(args, json_mode)
        return
    _pat_status()
    rc, out, err = _az(args)
    data = _json_parse_or_error(out, err, rc, json_mode)
    if data is None:
        return
    emit_ok({"status": "ok", "created": data}, json_mode=json_mode)


@cli.command("pr-list")
@click.option("--repository", default=None)
@click.option("--project", default=None)
@click.option("--status", "pr_status", type=click.Choice(["active", "completed", "abandoned", "all"]), default="active")
@click.option("--dry-run", is_flag=True)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def pr_list_cmd(
    repository: str | None,
    project: str | None,
    pr_status: str,
    dry_run: bool,
    json_mode: bool,
) -> None:
    """List pull requests."""
    args = ["repos", "pr", "list", "--status", pr_status, "-o", "json"]
    if repository:
        args.extend(["--repository", repository])
    if project:
        args.extend(["--project", project])
    if dry_run:
        _dry(args, json_mode)
        return
    _pat_status()
    rc, out, err = _az(args)
    data = _json_parse_or_error(out, err, rc, json_mode)
    if data is None:
        return
    emit_ok(
        {"status": "ok", "count": len(data) if isinstance(data, list) else 0, "prs": data},
        json_mode=json_mode,
    )


@cli.command("pr-create")
@click.option("--title", required=True)
@click.option("--source", required=True)
@click.option("--target", default="main", show_default=True)
@click.option("--repository", default=None)
@click.option("--description", default=None)
@click.option("--dry-run", is_flag=True)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def pr_create_cmd(
    title: str,
    source: str,
    target: str,
    repository: str | None,
    description: str | None,
    dry_run: bool,
    json_mode: bool,
) -> None:
    """Open a pull request."""
    args = [
        "repos",
        "pr",
        "create",
        "--title",
        title,
        "--source-branch",
        source,
        "--target-branch",
        target,
        "-o",
        "json",
    ]
    if repository:
        args.extend(["--repository", repository])
    if description:
        args.extend(["--description", description])
    if dry_run:
        _dry(args, json_mode)
        return
    _pat_status()
    rc, out, err = _az(args)
    data = _json_parse_or_error(out, err, rc, json_mode)
    if data is None:
        return
    emit_ok({"status": "ok", "pr": data}, json_mode=json_mode)


@cli.command("pipeline-list")
@click.option("--project", default=None)
@click.option("--dry-run", is_flag=True)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def pipe_list_cmd(project: str | None, dry_run: bool, json_mode: bool) -> None:
    """List pipelines."""
    args = ["pipelines", "list", "-o", "json"]
    if project:
        args.extend(["--project", project])
    if dry_run:
        _dry(args, json_mode)
        return
    _pat_status()
    rc, out, err = _az(args)
    data = _json_parse_or_error(out, err, rc, json_mode)
    if data is None:
        return
    emit_ok(
        {"status": "ok", "count": len(data) if isinstance(data, list) else 0, "pipelines": data},
        json_mode=json_mode,
    )


@cli.command("pipeline-run")
@click.argument("id_", metavar="ID", type=int)
@click.option("--branch", default=None)
@click.option("--project", default=None)
@click.option("--dry-run", is_flag=True)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def pipe_run_cmd(
    id_: int, branch: str | None, project: str | None, dry_run: bool, json_mode: bool
) -> None:
    """Queue a pipeline run."""
    args = ["pipelines", "run", "--id", str(id_), "-o", "json"]
    if branch:
        args.extend(["--branch", branch])
    if project:
        args.extend(["--project", project])
    if dry_run:
        _dry(args, json_mode)
        return
    _pat_status()
    rc, out, err = _az(args)
    data = _json_parse_or_error(out, err, rc, json_mode)
    if data is None:
        return
    emit_ok({"status": "ok", "run": data}, json_mode=json_mode)


if __name__ == "__main__":  # pragma: no cover
    cli()
