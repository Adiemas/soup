"""Tests for ``scripts.hydrate_context_excerpts``.

Focus areas:
  - Basic plumbing: parse findings → hydrate a plan → write JSON.
  - No-findings-left-out: unmatched rows land in ``plan.notes``.
  - Path-glob matching: ``files_allowed`` globs match correctly.
  - Agent gating: non-implementing agents are skipped.
  - Primary-only default filter.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.hydrate_context_excerpts import (
    Finding,
    hydrate,
    hydrate_files,
    parse_findings,
)

# ---------- parse_findings -------------------------------------------------


def test_parse_findings_basic() -> None:
    text = """# Research report

Some prose.

| File | Line | Relevance | Excerpt |
|---|---|---|---|
| `backend/app/api/calc.py` | 35-45 | primary — handler | `@router.post(...)` |
| `backend/app/services/combat.py` | 344-412 | primary | `for _ in range(iterations):` |
| `backend/app/clients/` | — | missing | _(absent)_ |

After the table.
"""
    findings = parse_findings(text)
    assert len(findings) == 3
    assert findings[0].file == "backend/app/api/calc.py"
    assert findings[0].line == "35-45"
    assert findings[0].is_primary
    assert findings[1].is_primary
    # "missing" relevance is not primary.
    assert not findings[2].is_primary


def test_parse_findings_ignores_non_table_content() -> None:
    text = "Just prose, no table here.\n\nNo pipes."
    assert parse_findings(text) == []


def test_parse_findings_handles_em_dash_in_relevance() -> None:
    # Researcher tables can carry em-dash (U+2014) or en-dash (U+2013)
    # in the relevance column — we match both as "primary".
    em = "\u2014"
    en = "\u2013"
    text = (
        "| File | Line | Relevance | Excerpt |\n"
        "|---|---|---|---|\n"
        f"| `a.py` | 1-5 | primary {em} detailed note | `x = 1` |\n"
        f"| `b.py` | 10 | primary {en} en-dash variant | `y = 2` |\n"
    )
    findings = parse_findings(text)
    assert len(findings) == 2
    assert all(f.is_primary for f in findings)


# ---------- Finding.as_context_entry --------------------------------------


def test_finding_as_context_entry_line_range() -> None:
    f = Finding(file="src/foo.py", line="10-20", relevance="primary")
    assert f.as_context_entry() == "src/foo.py:10-20"


def test_finding_as_context_entry_single_line_expanded() -> None:
    f = Finding(file="src/foo.py", line="42", relevance="primary")
    assert f.as_context_entry() == "src/foo.py:42-42"


def test_finding_as_context_entry_no_line() -> None:
    f = Finding(file="src/foo.py", line="—", relevance="secondary")
    # Em-dash lines fall back to bare path.
    assert f.as_context_entry() == "src/foo.py"


# ---------- hydrate (core) -------------------------------------------------


def test_hydrate_basic_plumbing() -> None:
    findings = [
        Finding(
            file="src/api/auth.py",
            line="35-45",
            relevance="primary",
        ),
        Finding(
            file="src/api/auth.py",
            line="100-120",
            relevance="primary",
        ),
    ]
    plan = {
        "goal": "Add login",
        "constitution_ref": "CONSTITUTION.md",
        "steps": [
            {
                "id": "S1",
                "agent": "python-dev",
                "prompt": "implement",
                "files_allowed": ["src/api/**"],
                "context_excerpts": [],
            }
        ],
    }
    result = hydrate(findings, plan)
    assert result.steps_hydrated == 1
    assert result.excerpts_added == 2
    excerpts = plan["steps"][0]["context_excerpts"]
    assert "src/api/auth.py:35-45" in excerpts
    assert "src/api/auth.py:100-120" in excerpts
    assert not result.unmatched


def test_hydrate_no_findings_left_out() -> None:
    """Unmatched findings must appear in ``plan.notes`` — never silently dropped."""
    findings = [
        # matches S1
        Finding(
            file="src/api/auth.py",
            line="10-20",
            relevance="primary",
        ),
        # matches nothing
        Finding(
            file="some/other/path.py",
            line="1-5",
            relevance="primary",
        ),
    ]
    plan = {
        "goal": "Add login",
        "constitution_ref": "CONSTITUTION.md",
        "steps": [
            {
                "id": "S1",
                "agent": "python-dev",
                "prompt": "implement",
                "files_allowed": ["src/api/**"],
                "context_excerpts": [],
            }
        ],
    }
    result = hydrate(findings, plan)
    assert result.excerpts_added == 1
    assert len(result.unmatched) == 1
    assert result.unmatched[0].file == "some/other/path.py"
    notes = plan.get("notes") or []
    assert any(
        "some/other/path.py" in n and "unmatched finding" in n for n in notes
    )


def test_hydrate_path_glob_matching() -> None:
    """Test various glob forms resolve correctly."""
    findings = [
        Finding(
            file="backend/app/api/combat.py",
            line="35",
            relevance="primary",
        ),
        Finding(
            file="backend/app/services/calc.py",
            line="100",
            relevance="primary",
        ),
        Finding(
            file="frontend/src/App.tsx",
            line="12-15",
            relevance="primary",
        ),
    ]
    plan = {
        "goal": "g",
        "constitution_ref": "CONSTITUTION.md",
        "steps": [
            {
                "id": "S_api",
                "agent": "python-dev",
                "prompt": "p",
                "files_allowed": ["backend/app/api/**"],
                "context_excerpts": [],
            },
            {
                "id": "S_services",
                "agent": "python-dev",
                "prompt": "p",
                "files_allowed": ["backend/app/services/*.py"],
                "context_excerpts": [],
            },
            {
                "id": "S_frontend",
                "agent": "react-dev",
                "prompt": "p",
                "files_allowed": ["frontend/src/**"],
                "context_excerpts": [],
            },
        ],
    }
    result = hydrate(findings, plan)
    assert result.excerpts_added == 3
    # Each step got its one matching finding.
    by_id = {s["id"]: s for s in plan["steps"]}
    assert "backend/app/api/combat.py:35-35" in by_id["S_api"]["context_excerpts"]
    assert (
        "backend/app/services/calc.py:100-100"
        in by_id["S_services"]["context_excerpts"]
    )
    assert (
        "frontend/src/App.tsx:12-15"
        in by_id["S_frontend"]["context_excerpts"]
    )


def test_hydrate_skips_non_implementing_agents() -> None:
    """Research/plan/QA agents don't get their own findings threaded back in."""
    findings = [
        Finding(
            file="src/foo.py",
            line="1-10",
            relevance="primary",
        ),
    ]
    plan = {
        "goal": "g",
        "constitution_ref": "CONSTITUTION.md",
        "steps": [
            {
                "id": "S0",
                "agent": "researcher",
                "prompt": "p",
                "files_allowed": ["src/**"],
                "context_excerpts": [],
            },
            {
                "id": "S1",
                "agent": "qa-orchestrator",
                "prompt": "p",
                "files_allowed": ["src/**"],
                "context_excerpts": [],
            },
        ],
    }
    result = hydrate(findings, plan)
    # No implementing steps → 0 hydrated. Finding goes to notes.
    assert result.steps_hydrated == 0
    assert result.excerpts_added == 0
    assert len(result.unmatched) == 1


def test_hydrate_primary_only_default() -> None:
    """Default filter drops secondary findings from context_excerpts."""
    findings = [
        Finding(file="a.py", line="1", relevance="primary"),
        Finding(file="a.py", line="2", relevance="secondary"),
    ]
    plan = {
        "goal": "g",
        "constitution_ref": "CONSTITUTION.md",
        "steps": [
            {
                "id": "S1",
                "agent": "python-dev",
                "prompt": "p",
                "files_allowed": ["a.py"],
                "context_excerpts": [],
            }
        ],
    }
    result = hydrate(findings, plan)
    assert result.excerpts_added == 1
    assert plan["steps"][0]["context_excerpts"] == ["a.py:1-1"]
    # Secondary is unmatched and lands in notes.
    assert len(result.unmatched) == 1
    assert result.unmatched[0].line == "2"


def test_hydrate_include_secondary_optional() -> None:
    """Passing ``primary_only=False`` lets secondary rows through."""
    findings = [
        Finding(file="a.py", line="2", relevance="secondary — minor"),
    ]
    plan = {
        "goal": "g",
        "constitution_ref": "CONSTITUTION.md",
        "steps": [
            {
                "id": "S1",
                "agent": "python-dev",
                "prompt": "p",
                "files_allowed": ["a.py"],
                "context_excerpts": [],
            }
        ],
    }
    result = hydrate(findings, plan, primary_only=False)
    assert result.excerpts_added == 1


def test_hydrate_dedups_existing_excerpts() -> None:
    """Re-running doesn't duplicate an already-present entry."""
    findings = [
        Finding(file="a.py", line="1-5", relevance="primary"),
    ]
    plan = {
        "goal": "g",
        "constitution_ref": "CONSTITUTION.md",
        "steps": [
            {
                "id": "S1",
                "agent": "python-dev",
                "prompt": "p",
                "files_allowed": ["a.py"],
                "context_excerpts": ["a.py:1-5"],
            }
        ],
    }
    result = hydrate(findings, plan)
    # Already present → no new additions.
    assert result.excerpts_added == 0
    # Existing entry unchanged.
    assert plan["steps"][0]["context_excerpts"] == ["a.py:1-5"]
    # And the finding is considered matched (not unmatched).
    assert not result.unmatched


def test_hydrate_skips_steps_with_empty_files_allowed() -> None:
    """``files_allowed = []`` means unbounded — skip to avoid surprise injects."""
    findings = [
        Finding(file="a.py", line="1", relevance="primary"),
    ]
    plan = {
        "goal": "g",
        "constitution_ref": "CONSTITUTION.md",
        "steps": [
            {
                "id": "S1",
                "agent": "python-dev",
                "prompt": "p",
                "files_allowed": [],
                "context_excerpts": [],
            }
        ],
    }
    result = hydrate(findings, plan)
    assert result.excerpts_added == 0
    assert len(result.unmatched) == 1


# ---------- hydrate_files (file-based wrapper) ----------------------------


def test_hydrate_files_end_to_end(tmp_path: Path) -> None:
    """End-to-end: read markdown + JSON, write hydrated JSON."""
    findings_md = tmp_path / "findings.md"
    findings_md.write_text(
        "# Research\n\n"
        "| File | Line | Relevance | Excerpt |\n"
        "|---|---|---|---|\n"
        "| `src/api/auth.py` | 10-20 | primary — login | `def login():` |\n",
        encoding="utf-8",
    )
    plan_json = tmp_path / "plan.json"
    plan_json.write_text(
        json.dumps(
            {
                "goal": "Add login",
                "constitution_ref": "CONSTITUTION.md",
                "steps": [
                    {
                        "id": "S1",
                        "agent": "python-dev",
                        "prompt": "implement login",
                        "files_allowed": ["src/api/**"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = hydrate_files(findings_md, plan_json)
    out_path = tmp_path / "plan-hydrated.json"
    assert out_path.exists(), f"default output file missing: {out_path}"
    out = json.loads(out_path.read_text(encoding="utf-8"))
    assert out["steps"][0]["context_excerpts"] == ["src/api/auth.py:10-20"]
    assert result.excerpts_added == 1


def test_hydrate_files_custom_output(tmp_path: Path) -> None:
    """``output_path`` overrides the default ``<plan>-hydrated.json``."""
    findings_md = tmp_path / "findings.md"
    findings_md.write_text(
        "| File | Line | Relevance | Excerpt |\n"
        "|---|---|---|---|\n"
        "| `x.py` | 1-1 | primary | `x` |\n",
        encoding="utf-8",
    )
    plan_json = tmp_path / "plan.json"
    plan_json.write_text(
        json.dumps(
            {
                "goal": "g",
                "constitution_ref": "c",
                "steps": [
                    {
                        "id": "S1",
                        "agent": "python-dev",
                        "prompt": "p",
                        "files_allowed": ["x.py"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    custom_out = tmp_path / "my-output.json"
    hydrate_files(findings_md, plan_json, output_path=custom_out)
    assert custom_out.exists()
    assert not (tmp_path / "plan-hydrated.json").exists()
