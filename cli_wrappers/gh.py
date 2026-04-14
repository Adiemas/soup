"""gh-wrap — agent-callable GitHub CLI wrapper.

Wraps ``gh``. Uses ``GITHUB_TOKEN`` from env (gh auto-reads this).

Subcommands:
- pr-list
- pr-view <number>
- pr-create
- issue-list
- issue-create
- run-list       — GitHub Actions workflow runs
- run-view <id>
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import click

from . import emit_error, emit_ok, run_cmd


def _token_status() -> bool:
    """Report whether GITHUB_TOKEN is set (gh reads it automatically)."""
    if os.environ.get("GITHUB_TOKEN"):
        return True
    sys.stderr.write(
        "[gh-wrap] WARNING: GITHUB_TOKEN not set; gh may prompt or fail\n"
    )
    return False


def _gh(args: list[str]) -> tuple[int, str, str]:
    """Invoke ``gh`` with args; return (rc, stdout, stderr)."""
    res = run_cmd(["gh", *args], check=False, timeout=180.0)
    return res.returncode, res.stdout, res.stderr


def _json_parse_or_error(stdout: str, stderr: str, rc: int, json_mode: bool) -> Any:
    """Parse gh JSON output; emit structured error on failure."""
    if rc != 0:
        emit_error(stderr.strip() or "gh command failed", code=rc, json_mode=json_mode)
        return None
    if not stdout.strip():
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        emit_error(f"gh returned non-JSON: {e}", code=1, json_mode=json_mode)
        return None


@click.group(name="gh-wrap", help="JSON-first GitHub CLI wrapper for soup agents.")
def cli() -> None:
    """Root command group."""


_PR_FIELDS = "number,title,author,state,headRefName,baseRefName,url,mergeable,createdAt,updatedAt"
_ISSUE_FIELDS = "number,title,author,state,labels,url,createdAt,updatedAt"
_RUN_FIELDS = "databaseId,name,status,conclusion,headBranch,headSha,workflowName,url,createdAt"


@cli.command("pr-list")
@click.option("--repo", "-R", default=None)
@click.option("--state", default="open", show_default=True)
@click.option("--limit", default=30, type=int, show_default=True)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def pr_list_cmd(repo: str | None, state: str, limit: int, json_mode: bool) -> None:
    """List pull requests."""
    _token_status()
    args = ["pr", "list", "--state", state, "--limit", str(limit), "--json", _PR_FIELDS]
    if repo:
        args.extend(["-R", repo])
    rc, out, err = _gh(args)
    data = _json_parse_or_error(out, err, rc, json_mode)
    if data is None:
        return
    emit_ok(
        {"status": "ok", "count": len(data) if isinstance(data, list) else 0, "prs": data},
        json_mode=json_mode,
    )


@cli.command("pr-view")
@click.argument("number", type=int)
@click.option("--repo", "-R", default=None)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def pr_view_cmd(number: int, repo: str | None, json_mode: bool) -> None:
    """View a pull request."""
    _token_status()
    fields = _PR_FIELDS + ",body,files,reviews,statusCheckRollup"
    args = ["pr", "view", str(number), "--json", fields]
    if repo:
        args.extend(["-R", repo])
    rc, out, err = _gh(args)
    data = _json_parse_or_error(out, err, rc, json_mode)
    if data is None:
        return
    emit_ok({"status": "ok", "pr": data}, json_mode=json_mode)


@cli.command("pr-create")
@click.option("--title", required=True)
@click.option("--body", default="")
@click.option("--base", default="main", show_default=True)
@click.option("--head", default=None)
@click.option("--repo", "-R", default=None)
@click.option("--draft", is_flag=True)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def pr_create_cmd(
    title: str,
    body: str,
    base: str,
    head: str | None,
    repo: str | None,
    draft: bool,
    json_mode: bool,
) -> None:
    """Open a pull request."""
    _token_status()
    args = ["pr", "create", "--title", title, "--body", body, "--base", base]
    if head:
        args.extend(["--head", head])
    if draft:
        args.append("--draft")
    if repo:
        args.extend(["-R", repo])
    rc, out, err = _gh(args)
    if rc != 0:
        emit_error(err.strip() or out.strip() or "gh pr create failed", rc, json_mode=json_mode)
        return
    # gh pr create returns the URL on stdout.
    url = out.strip().splitlines()[-1] if out.strip() else ""
    emit_ok({"status": "ok", "url": url}, json_mode=json_mode)


@cli.command("issue-list")
@click.option("--repo", "-R", default=None)
@click.option("--state", default="open", show_default=True)
@click.option("--limit", default=30, type=int, show_default=True)
@click.option("--label", default=None)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def issue_list_cmd(
    repo: str | None, state: str, limit: int, label: str | None, json_mode: bool
) -> None:
    """List issues."""
    _token_status()
    args = [
        "issue",
        "list",
        "--state",
        state,
        "--limit",
        str(limit),
        "--json",
        _ISSUE_FIELDS,
    ]
    if label:
        args.extend(["--label", label])
    if repo:
        args.extend(["-R", repo])
    rc, out, err = _gh(args)
    data = _json_parse_or_error(out, err, rc, json_mode)
    if data is None:
        return
    emit_ok(
        {"status": "ok", "count": len(data) if isinstance(data, list) else 0, "issues": data},
        json_mode=json_mode,
    )


@cli.command("issue-create")
@click.option("--title", required=True)
@click.option("--body", default="")
@click.option("--repo", "-R", default=None)
@click.option("--label", "labels", multiple=True)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def issue_create_cmd(
    title: str,
    body: str,
    repo: str | None,
    labels: tuple[str, ...],
    json_mode: bool,
) -> None:
    """Create a new issue."""
    _token_status()
    args = ["issue", "create", "--title", title, "--body", body]
    for lbl in labels:
        args.extend(["--label", lbl])
    if repo:
        args.extend(["-R", repo])
    rc, out, err = _gh(args)
    if rc != 0:
        emit_error(err.strip() or "gh issue create failed", rc, json_mode=json_mode)
        return
    url = out.strip().splitlines()[-1] if out.strip() else ""
    emit_ok({"status": "ok", "url": url}, json_mode=json_mode)


@cli.command("run-list")
@click.option("--repo", "-R", default=None)
@click.option("--workflow", "-w", default=None)
@click.option("--limit", default=20, type=int, show_default=True)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def run_list_cmd(
    repo: str | None, workflow: str | None, limit: int, json_mode: bool
) -> None:
    """List Actions workflow runs."""
    _token_status()
    args = ["run", "list", "--limit", str(limit), "--json", _RUN_FIELDS]
    if workflow:
        args.extend(["-w", workflow])
    if repo:
        args.extend(["-R", repo])
    rc, out, err = _gh(args)
    data = _json_parse_or_error(out, err, rc, json_mode)
    if data is None:
        return
    emit_ok(
        {"status": "ok", "count": len(data) if isinstance(data, list) else 0, "runs": data},
        json_mode=json_mode,
    )


@cli.command("run-view")
@click.argument("id_", metavar="ID")
@click.option("--repo", "-R", default=None)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def run_view_cmd(id_: str, repo: str | None, json_mode: bool) -> None:
    """View details of a single Actions run."""
    _token_status()
    fields = _RUN_FIELDS + ",jobs"
    args = ["run", "view", id_, "--json", fields]
    if repo:
        args.extend(["-R", repo])
    rc, out, err = _gh(args)
    data = _json_parse_or_error(out, err, rc, json_mode)
    if data is None:
        return
    emit_ok({"status": "ok", "run": data}, json_mode=json_mode)


if __name__ == "__main__":  # pragma: no cover
    cli()
