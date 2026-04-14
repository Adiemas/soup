"""dotnet-wrap — agent-callable .NET 8 CLI wrapper.

Subcommands:
- build
- test [--filter X]   — parses xUnit .trx output where available
- run <project>
- pack
- ef-migrate <name>
- ef-update
- ef-script [--from X --to Y] [--idempotent] [--output PATH]
- ef-remove [--force]
- ef-list [--json]
- format [--verify]
"""

from __future__ import annotations

import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import click

from . import SoupWrapperError, emit_error, emit_ok, run_cmd


def _dotnet(args: list[str], *, timeout: float = 1200.0) -> tuple[int, str, str]:
    """Run ``dotnet`` and return (returncode, stdout, stderr)."""
    res = run_cmd(["dotnet", *args], check=False, timeout=timeout)
    return res.returncode, res.stdout, res.stderr


@click.group(name="dotnet-wrap", help="JSON-first dotnet wrapper for soup agents.")
def cli() -> None:
    """Root command group."""


@cli.command("build")
@click.option("--configuration", "-c", default="Debug", show_default=True)
@click.option("--project", default=None)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def build_cmd(configuration: str, project: str | None, json_mode: bool) -> None:
    """Build the current solution/project."""
    try:
        args = ["build", "-c", configuration, "--nologo"]
        if project:
            args.append(project)
        rc, out, err = _dotnet(args)
        tail_out = "\n".join(out.splitlines()[-40:])
        tail_err = "\n".join(err.splitlines()[-20:])
        if rc != 0:
            emit_error(
                tail_err or tail_out or "dotnet build failed",
                code=rc,
                json_mode=json_mode,
            )
        else:
            emit_ok(
                {
                    "status": "ok",
                    "configuration": configuration,
                    "project": project,
                    "stdout_tail": tail_out,
                },
                json_mode=json_mode,
            )
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


def _parse_trx(trx_path: Path) -> dict[str, Any]:
    """Parse a VSTest TRX file into a summary dict."""
    try:
        tree = ET.parse(trx_path)
    except ET.ParseError as e:
        return {"parse_error": str(e)}
    root = tree.getroot()
    ns = {"v": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}
    summary = root.find("v:ResultSummary/v:Counters", ns)
    counts: dict[str, int] = {}
    if summary is not None:
        for k in ("total", "executed", "passed", "failed", "error", "skipped"):
            v = summary.attrib.get(k)
            if v is not None and v.isdigit():
                counts[k] = int(v)
    failures: list[dict[str, str]] = []
    for r in root.findall(".//v:UnitTestResult", ns):
        if r.attrib.get("outcome") == "Failed":
            name = r.attrib.get("testName", "")
            msg_el = r.find(".//v:Message", ns)
            msg = msg_el.text if msg_el is not None and msg_el.text else ""
            failures.append({"test": name, "message": msg.strip()[:500]})
    return {"counts": counts, "failures": failures}


@cli.command("test")
@click.option("--filter", "test_filter", default=None, help="xUnit filter expression.")
@click.option("--project", default=None)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def test_cmd(test_filter: str | None, project: str | None, json_mode: bool) -> None:
    """Run tests (xUnit) and return structured results."""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            trx = Path(tmp) / "results.trx"
            args = [
                "test",
                "--nologo",
                "--logger",
                f"trx;LogFileName={trx}",
                "--results-directory",
                str(trx.parent),
            ]
            if test_filter:
                args.extend(["--filter", test_filter])
            if project:
                args.append(project)
            rc, out, err = _dotnet(args, timeout=1800.0)
            trx_data: dict[str, Any] = {}
            # dotnet may substitute filename; find the generated .trx under tmp.
            trx_files = list(Path(tmp).rglob("*.trx"))
            if trx_files:
                trx_data = _parse_trx(trx_files[0])
            payload: dict[str, Any] = {
                "status": "ok" if rc == 0 else "error",
                "returncode": rc,
                "filter": test_filter,
                "project": project,
                "counts": trx_data.get("counts", {}),
                "failures": trx_data.get("failures", []),
                "stdout_tail": "\n".join(out.splitlines()[-30:]),
            }
            if rc != 0:
                emit_error(
                    f"tests failed ({rc}); failures={len(payload['failures'])}",
                    code=rc,
                    json_mode=json_mode,
                )
            else:
                emit_ok(payload, json_mode=json_mode)
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("run")
@click.argument("project")
@click.option("--configuration", "-c", default="Debug", show_default=True)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
@click.argument("extra", nargs=-1)
def run_project_cmd(
    project: str, configuration: str, json_mode: bool, extra: tuple[str, ...]
) -> None:
    """Run a .NET project (blocks; use for short-lived commands)."""
    try:
        args = ["run", "--project", project, "-c", configuration]
        if extra:
            args.append("--")
            args.extend(list(extra))
        rc, out, err = _dotnet(args, timeout=600.0)
        if rc != 0:
            emit_error(
                err.strip() or "dotnet run failed", code=rc, json_mode=json_mode
            )
        else:
            emit_ok(
                {"status": "ok", "project": project, "stdout": out, "stderr": err},
                json_mode=json_mode,
            )
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("pack")
@click.option("--configuration", "-c", default="Release", show_default=True)
@click.option("--project", default=None)
@click.option("--output", "-o", default=None)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def pack_cmd(
    configuration: str, project: str | None, output: str | None, json_mode: bool
) -> None:
    """Pack NuGet artifacts."""
    try:
        args = ["pack", "-c", configuration, "--nologo"]
        if output:
            args.extend(["-o", output])
        if project:
            args.append(project)
        rc, out, err = _dotnet(args)
        if rc != 0:
            emit_error(err.strip() or "dotnet pack failed", code=rc, json_mode=json_mode)
        else:
            emit_ok(
                {"status": "ok", "configuration": configuration, "output": output, "log": out[-800:]},
                json_mode=json_mode,
            )
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("ef-migrate")
@click.argument("name")
@click.option("--project", default=None, help="Project containing DbContext.")
@click.option("--startup-project", default=None)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def ef_migrate_cmd(
    name: str, project: str | None, startup_project: str | None, json_mode: bool
) -> None:
    """Create an EF Core migration."""
    try:
        args = ["ef", "migrations", "add", name]
        if project:
            args.extend(["--project", project])
        if startup_project:
            args.extend(["--startup-project", startup_project])
        rc, out, err = _dotnet(args)
        if rc != 0:
            emit_error(err.strip() or "ef migrations add failed", code=rc, json_mode=json_mode)
        else:
            emit_ok({"status": "ok", "name": name, "log": out[-800:]}, json_mode=json_mode)
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("ef-update")
@click.option("--project", default=None)
@click.option("--startup-project", default=None)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def ef_update_cmd(project: str | None, startup_project: str | None, json_mode: bool) -> None:
    """Apply EF Core migrations to the database."""
    try:
        args = ["ef", "database", "update"]
        if project:
            args.extend(["--project", project])
        if startup_project:
            args.extend(["--startup-project", startup_project])
        rc, out, err = _dotnet(args)
        if rc != 0:
            emit_error(err.strip() or "ef database update failed", code=rc, json_mode=json_mode)
        else:
            emit_ok({"status": "ok", "log": out[-800:]}, json_mode=json_mode)
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("ef-script")
@click.option(
    "--from",
    "from_migration",
    default=None,
    help="Source migration name (forward baseline; omit for '0' / initial).",
)
@click.option(
    "--to",
    "to_migration",
    default=None,
    help="Target migration name (reverse when from > to).",
)
@click.option(
    "--idempotent/--no-idempotent",
    "idempotent",
    default=False,
    show_default=True,
    help="Emit an idempotent script safe to re-run.",
)
@click.option(
    "--output",
    "-o",
    "output",
    default=None,
    help="Write SQL to this file instead of stdout.",
)
@click.option("--project", default=None, help="Project containing DbContext.")
@click.option("--startup-project", default=None)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def ef_script_cmd(
    from_migration: str | None,
    to_migration: str | None,
    idempotent: bool,
    output: str | None,
    project: str | None,
    startup_project: str | None,
    json_mode: bool,
) -> None:
    """Generate raw SQL from EF Core migrations (forward or reverse)."""
    try:
        args: list[str] = ["ef", "migrations", "script"]
        if from_migration is not None:
            args.append(from_migration)
            # `ef migrations script FROM TO` — TO positional only makes sense when FROM is given.
            if to_migration is not None:
                args.append(to_migration)
        if idempotent:
            args.append("--idempotent")
        if output:
            args.extend(["--output", output])
        if project:
            args.extend(["--project", project])
        if startup_project:
            args.extend(["--startup-project", startup_project])
        rc, out, err = _dotnet(args)
        if rc != 0:
            emit_error(
                err.strip() or "ef migrations script failed",
                code=rc,
                json_mode=json_mode,
            )
        else:
            emit_ok(
                {
                    "status": "ok",
                    "from": from_migration,
                    "to": to_migration,
                    "idempotent": idempotent,
                    "output": output,
                    "sql_tail": out[-800:] if not output else None,
                },
                json_mode=json_mode,
            )
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("ef-remove")
@click.option(
    "--force/--no-force",
    "force",
    default=False,
    show_default=True,
    help="Revert the migration if it has been applied.",
)
@click.option("--project", default=None)
@click.option("--startup-project", default=None)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def ef_remove_cmd(
    force: bool,
    project: str | None,
    startup_project: str | None,
    json_mode: bool,
) -> None:
    """Remove the last EF Core migration."""
    try:
        args: list[str] = ["ef", "migrations", "remove"]
        if force:
            args.append("--force")
        if project:
            args.extend(["--project", project])
        if startup_project:
            args.extend(["--startup-project", startup_project])
        rc, out, err = _dotnet(args)
        if rc != 0:
            emit_error(
                err.strip() or "ef migrations remove failed",
                code=rc,
                json_mode=json_mode,
            )
        else:
            emit_ok(
                {"status": "ok", "force": force, "log": out[-800:]},
                json_mode=json_mode,
            )
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("ef-list")
@click.option(
    "--json/--no-json",
    "json_mode",
    default=True,
    show_default=True,
    help="Emit structured JSON; passes --json through to dotnet ef.",
)
@click.option("--project", default=None)
@click.option("--startup-project", default=None)
def ef_list_cmd(
    json_mode: bool, project: str | None, startup_project: str | None
) -> None:
    """List EF Core migrations; passes ``--json`` to dotnet ef when set."""
    try:
        args: list[str] = ["ef", "migrations", "list"]
        if json_mode:
            args.append("--json")
        if project:
            args.extend(["--project", project])
        if startup_project:
            args.extend(["--startup-project", startup_project])
        rc, out, err = _dotnet(args)
        if rc != 0:
            emit_error(
                err.strip() or "ef migrations list failed",
                code=rc,
                json_mode=json_mode,
            )
            return
        migrations: list[Any] = []
        parsed_ok = False
        if json_mode and out.strip():
            # `dotnet ef --json` wraps its JSON in //BEGIN / //END markers.
            text = out
            begin = text.find("//BEGIN")
            end = text.rfind("//END")
            if begin != -1 and end != -1 and end > begin:
                body = text[begin + len("//BEGIN") : end].strip()
                try:
                    migrations = json.loads(body)
                    parsed_ok = True
                except ValueError:
                    parsed_ok = False
            if not parsed_ok:
                # Fall back to line-wise hunt for a JSON array.
                for line in text.splitlines():
                    line = line.strip()
                    if line.startswith("[") and line.endswith("]"):
                        try:
                            migrations = json.loads(line)
                            parsed_ok = True
                            break
                        except ValueError:
                            continue
        emit_ok(
            {
                "status": "ok",
                "count": len(migrations),
                "migrations": migrations,
                "parsed": parsed_ok,
                "stdout_tail": "\n".join(out.splitlines()[-20:]),
            },
            json_mode=json_mode,
        )
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("format")
@click.option(
    "--verify/--no-verify",
    "verify",
    default=False,
    show_default=True,
    help="CI mode: pass --verify-no-changes and fail if unformatted files exist.",
)
@click.option("--project", default=None, help="Project or solution to format.")
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def format_cmd(verify: bool, project: str | None, json_mode: bool) -> None:
    """Run `dotnet format`; `--verify` implies `--verify-no-changes` (CI)."""
    try:
        args: list[str] = ["format"]
        if project:
            args.append(project)
        if verify:
            args.append("--verify-no-changes")
        rc, out, err = _dotnet(args)
        tail_out = "\n".join(out.splitlines()[-40:])
        tail_err = "\n".join(err.splitlines()[-20:])
        if rc != 0:
            emit_error(
                tail_err or tail_out or "dotnet format failed",
                code=rc,
                json_mode=json_mode,
            )
        else:
            emit_ok(
                {
                    "status": "ok",
                    "verify": verify,
                    "project": project,
                    "stdout_tail": tail_out,
                },
                json_mode=json_mode,
            )
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


if __name__ == "__main__":  # pragma: no cover
    cli()
