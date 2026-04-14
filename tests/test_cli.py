"""Tests for ``orchestrator.cli`` — logs tree / logs search / cost-report.

Covers the iter-3 ε4 additions: `soup logs tree <run_id>` reconstructs
from JSONL alone, `soup logs search` filters by regex + agent, and
`soup cost-report` aggregates `experiments.tsv` by the requested
grouping key.

Each test writes fixture data to a ``tmp_path`` tree and invokes the
Typer app in-process via the CliRunner — no subprocesses, no real log
files touched.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from orchestrator.cli import app

runner = CliRunner()


def _write_session_jsonl(
    log_dir: Path,
    session_id: str,
    entries: list[dict],
) -> None:
    """Write a session JSONL file with *entries* — one line per dict."""
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"session-{session_id}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for rec in entries:
            fh.write(json.dumps(rec) + "\n")


def test_logs_tree_reconstructs_from_mock_jsonl(tmp_path: Path) -> None:
    """`soup logs tree <run_id>` renders parent->child from JSONL alone.

    Fixture: three sessions in the same run. The orchestrator spawns a
    wave-0 implementer; the implementer spawns a wave-1 verifier. Each
    session carries the right ``root_run_id`` + ``parent_session_id``
    on at least one of its entries.
    """
    run_id = "run-2026-04-14-abc"
    log_dir = tmp_path / "logging" / "agent-runs"

    # Root orchestrator session — has no parent inside this run.
    _write_session_jsonl(
        log_dir,
        "orch-root",
        [
            {
                "ts": "2026-04-14T09:00:00Z",
                "session_id": "orch-root",
                "agent": "orchestrator",
                "action": "Spawn",
                "root_run_id": run_id,
                "parent_session_id": None,
                "wave_idx": 0,
                "step_id": "S0",
                "status": "started",
                "duration_ms": 0,
            }
        ],
    )
    # Implementer spawned by the orchestrator in wave 0.
    _write_session_jsonl(
        log_dir,
        "impl-1",
        [
            {
                "ts": "2026-04-14T09:00:05Z",
                "session_id": "impl-1",
                "agent": "implementer",
                "action": "Edit",
                "root_run_id": run_id,
                "parent_session_id": "orch-root",
                "wave_idx": 0,
                "step_id": "S1",
                "status": "started",
                "duration_ms": 0,
            }
        ],
    )
    # Verifier spawned by the implementer in wave 1.
    _write_session_jsonl(
        log_dir,
        "verif-1",
        [
            {
                "ts": "2026-04-14T09:00:30Z",
                "session_id": "verif-1",
                "agent": "verifier",
                "action": "Bash",
                "root_run_id": run_id,
                "parent_session_id": "impl-1",
                "wave_idx": 1,
                "step_id": "S2",
                "status": "started",
                "duration_ms": 0,
            }
        ],
    )
    # Add a noise session that belongs to a different run — must not
    # appear in the tree.
    _write_session_jsonl(
        log_dir,
        "other-run",
        [
            {
                "ts": "2026-04-14T10:00:00Z",
                "session_id": "other-run",
                "agent": "implementer",
                "action": "Edit",
                "root_run_id": "run-different",
                "parent_session_id": None,
                "wave_idx": 0,
                "step_id": "S1",
                "status": "started",
                "duration_ms": 0,
            }
        ],
    )

    result = runner.invoke(
        app, ["logs", "tree", run_id, "--log-dir", str(log_dir)]
    )
    assert result.exit_code == 0, result.output
    # All three in-run sessions render; the foreign session does not.
    assert "orch-root" in result.output
    assert "impl-1" in result.output
    assert "verif-1" in result.output
    assert "other-run" not in result.output
    # Indentation: verif-1 (depth 2) should be more indented than
    # impl-1 (depth 1), which should be more indented than orch-root
    # (depth 0).
    lines = {
        name: next(
            (ln for ln in result.output.splitlines() if name in ln), None
        )
        for name in ("orch-root", "impl-1", "verif-1")
    }
    assert all(lines.values())
    indent_orch = len(lines["orch-root"]) - len(lines["orch-root"].lstrip())
    indent_impl = len(lines["impl-1"]) - len(lines["impl-1"].lstrip())
    indent_verif = len(lines["verif-1"]) - len(lines["verif-1"].lstrip())
    assert indent_orch < indent_impl < indent_verif


def test_logs_search_filters_by_agent_and_regex(tmp_path: Path) -> None:
    """`soup logs search <pattern> --agent <name>` filters correctly.

    Fixture: two sessions carrying different agents + different events.
    The search matches only one line once the agent filter is applied.
    """
    log_dir = tmp_path / "logging" / "agent-runs"
    _write_session_jsonl(
        log_dir,
        "impl-1",
        [
            {
                "ts": "2026-04-14T09:00:00Z",
                "session_id": "impl-1",
                "agent": "implementer",
                "action": "Edit",
                "input_summary": "Order.Place_completed order_id=1",
                "status": "success",
                "duration_ms": 5,
            },
            {
                "ts": "2026-04-14T09:00:05Z",
                "session_id": "impl-1",
                "agent": "implementer",
                "action": "Bash",
                "input_summary": "pytest",
                "status": "success",
                "duration_ms": 900,
            },
        ],
    )
    _write_session_jsonl(
        log_dir,
        "verif-1",
        [
            {
                "ts": "2026-04-14T09:00:30Z",
                "session_id": "verif-1",
                "agent": "verifier",
                "action": "Bash",
                "input_summary": "Order.Place_completed verify",
                "status": "success",
                "duration_ms": 100,
            }
        ],
    )

    # Without an agent filter: both lines that carry the substring match.
    result_all = runner.invoke(
        app,
        [
            "logs",
            "search",
            "Order.Place_completed",
            "--log-dir",
            str(log_dir),
        ],
    )
    assert result_all.exit_code == 0, result_all.output
    assert "(2 matches)" in result_all.output

    # Agent filter narrows to the implementer-only match.
    result_filtered = runner.invoke(
        app,
        [
            "logs",
            "search",
            "Order.Place_completed",
            "--agent",
            "implementer",
            "--log-dir",
            str(log_dir),
        ],
    )
    assert result_filtered.exit_code == 0, result_filtered.output
    assert "(1 matches)" in result_filtered.output
    assert "impl-1" in result_filtered.output
    assert "verif-1" not in result_filtered.output


def test_cost_report_aggregates_mock_tsv(tmp_path: Path) -> None:
    """`soup cost-report --group-by run` sums cost_usd per run."""
    tsv = tmp_path / "experiments.tsv"
    tsv.write_text(
        "# soup-schema:experiments-v1\n"
        "ts\trun_id\tstatus\tduration_sec\tn_steps\tbudget_sec\tcost_usd\taborted_reason\tgoal\n"
        "2026-04-10T10:00:00Z\tR1\tpassed\t120\t3\t3600\t~0.5000\t-\tadd ping\n"
        "2026-04-11T10:00:00Z\tR2\tpassed\t300\t5\t3600\t~1.2500\t-\trefactor auth\n"
        "2026-04-12T10:00:00Z\tR3\tpassed\t60\t2\t3600\t~0.1000\t-\tfix typo\n",
        encoding="utf-8",
    )

    # Aggregate by run — each run is its own bucket.
    result = runner.invoke(
        app,
        [
            "cost-report",
            "--group-by",
            "run",
            "--experiments-tsv",
            str(tsv),
        ],
    )
    assert result.exit_code == 0, result.output
    for run_id in ("R1", "R2", "R3"):
        assert run_id in result.output
    # Total line sums all three.
    assert "total: ~$1.8500" in result.output

    # --since filter excludes R1.
    result_since = runner.invoke(
        app,
        [
            "cost-report",
            "--group-by",
            "run",
            "--since",
            "2026-04-11",
            "--experiments-tsv",
            str(tsv),
        ],
    )
    assert result_since.exit_code == 0, result_since.output
    assert "R2" in result_since.output
    assert "R3" in result_since.output
    assert "R1" not in result_since.output
    assert "total: ~$1.3500" in result_since.output
