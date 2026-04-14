"""Unit tests for ``schemas/*.py``."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from schemas import (
    AgentLogEntry,
    ExecutionPlan,
    ExecutionPlanValidator,
    Finding,
    QAReport,
    Spec,
    Task,
    TaskStep,
    TestResults,
    load_agent_roster,
)
from schemas.execution_plan import get_active_roster, set_active_roster

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_ROSTER = {
    "orchestrator",
    "meta-prompter",
    "architect",
    "implementer",
    "python-dev",
    "test-engineer",
    "code-reviewer",
    "verifier",
}


@pytest.fixture
def library_file(tmp_path: Path) -> Path:
    """Minimal library.yaml that exposes only our test roster."""
    data = {
        "version": 1,
        "catalog": [
            {"name": name, "type": "agent", "source": f"local:{name}.md"}
            for name in sorted(_ROSTER)
        ],
    }
    p = tmp_path / "library.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    return p


@pytest.fixture
def sample_plan() -> ExecutionPlan:
    return ExecutionPlan(
        goal="Add a /ping endpoint",
        constitution_ref="CONSTITUTION.md",
        steps=[
            TaskStep(
                id="S1",
                agent="test-engineer",
                prompt="Write a failing test for GET /ping returning 200.",
                verify_cmd="pytest tests/test_ping.py",
                files_allowed=["tests/**"],
            ),
            TaskStep(
                id="S2",
                agent="implementer",
                prompt="Implement GET /ping to make the test pass.",
                depends_on=["S1"],
                verify_cmd="pytest tests/test_ping.py",
                files_allowed=["app/**"],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# ExecutionPlan / TaskStep / ExecutionPlanValidator
# ---------------------------------------------------------------------------


def test_execution_plan_minimal_construction(sample_plan: ExecutionPlan) -> None:
    assert len(sample_plan.steps) == 2
    assert sample_plan.budget_sec == 3600
    assert sample_plan.worktree is True


def test_taskstep_rejects_self_dependency() -> None:
    with pytest.raises(ValidationError):
        TaskStep(
            id="S1",
            agent="implementer",
            prompt="p",
            verify_cmd="true",
            depends_on=["S1"],
        )


def test_execution_plan_rejects_duplicate_ids() -> None:
    with pytest.raises(ValidationError):
        ExecutionPlan(
            goal="g",
            constitution_ref="CONSTITUTION.md",
            steps=[
                TaskStep(id="S1", agent="implementer", prompt="p", verify_cmd="true"),
                TaskStep(id="S1", agent="implementer", prompt="q", verify_cmd="true"),
            ],
        )


def test_validator_flags_missing_dependency(
    sample_plan: ExecutionPlan, library_file: Path
) -> None:
    bad = sample_plan.model_copy(deep=True)
    bad.steps[1].depends_on = ["S99"]
    validator = ExecutionPlanValidator.from_library(library_file)
    with pytest.raises(ValueError, match="unknown step"):
        validator.validate(bad)


def test_validator_flags_cycle(library_file: Path) -> None:
    plan = ExecutionPlan(
        goal="g",
        constitution_ref="CONSTITUTION.md",
        steps=[
            TaskStep(
                id="A",
                agent="implementer",
                prompt="p",
                verify_cmd="true",
                depends_on=["B"],
            ),
            TaskStep(
                id="B",
                agent="implementer",
                prompt="p",
                verify_cmd="true",
                depends_on=["A"],
            ),
        ],
    )
    validator = ExecutionPlanValidator.from_library(library_file)
    with pytest.raises(ValueError, match="cycle"):
        validator.validate(plan)


def test_validator_flags_unknown_agent(
    sample_plan: ExecutionPlan, library_file: Path
) -> None:
    bad = sample_plan.model_copy(deep=True)
    bad.steps[0].agent = "blender-designer"  # not in the roster
    validator = ExecutionPlanValidator.from_library(library_file)
    with pytest.raises(ValueError, match="not in the roster"):
        validator.validate(bad)


def test_load_agent_roster_accepts_project_library() -> None:
    roster = load_agent_roster(Path("library.yaml"))
    # spot-check core agents; file is part of the repo
    assert {"orchestrator", "meta-prompter", "verifier"} <= roster


# ---------------------------------------------------------------------------
# TaskStep.agent field validator (H10) — passes when agent is in roster,
# raises ValidationError at parse time when it isn't.
# ---------------------------------------------------------------------------


def test_taskstep_agent_field_validator_accepts_known_agent() -> None:
    """Valid agent name passes the parse-time field validator."""
    prior = get_active_roster()
    try:
        set_active_roster({"implementer", "verifier", "test-engineer"})
        step = TaskStep(
            id="S1",
            agent="implementer",
            prompt="do the thing",
            verify_cmd="true",
        )
        assert step.agent == "implementer"
    finally:
        set_active_roster(prior)


def test_taskstep_agent_field_validator_rejects_unknown_agent() -> None:
    """Unknown agent name fails at parse time (Pydantic ValidationError)."""
    prior = get_active_roster()
    try:
        set_active_roster({"implementer", "verifier", "test-engineer"})
        with pytest.raises(ValidationError, match="not in the roster"):
            TaskStep(
                id="S1",
                agent="ghost-agent",
                prompt="do the thing",
                verify_cmd="true",
            )
    finally:
        set_active_roster(prior)


def test_taskstep_context_excerpts_accepts_path_anchor(tmp_path: Path) -> None:
    """``context_excerpts`` accepts ``path#anchor`` when the path exists."""
    prior = get_active_roster()
    original_cwd = Path.cwd()
    import os

    try:
        set_active_roster({"implementer", "test-engineer", "verifier"})
        os.chdir(tmp_path)
        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()
        spec_path = spec_dir / "combat.md"
        spec_path.write_text("# Spec\n## phase-1\n content\n", encoding="utf-8")
        step = TaskStep(
            id="S1",
            agent="implementer",
            prompt="use this spec",
            verify_cmd="true",
            context_excerpts=["specs/combat.md#phase-1"],
        )
        assert step.context_excerpts == ["specs/combat.md#phase-1"]
        library = tmp_path / "library.yaml"
        library.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "catalog": [
                        {"name": "implementer", "type": "agent", "source": "x"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        plan = ExecutionPlan(
            goal="g",
            constitution_ref="CONSTITUTION.md",
            steps=[step],
        )
        ExecutionPlanValidator.from_library(library).validate(plan)
    finally:
        os.chdir(original_cwd)
        set_active_roster(prior)


def test_taskstep_context_excerpts_accepts_line_range(tmp_path: Path) -> None:
    """``context_excerpts`` accepts ``path:line_from-line_to`` form."""
    prior = get_active_roster()
    original_cwd = Path.cwd()
    import os

    try:
        set_active_roster({"implementer"})
        os.chdir(tmp_path)
        src_dir = tmp_path / "src" / "api"
        src_dir.mkdir(parents=True)
        src_path = src_dir / "auth.py"
        src_path.write_text(
            "\n".join(f"# line {i}" for i in range(1, 100)) + "\n",
            encoding="utf-8",
        )
        step = TaskStep(
            id="S1",
            agent="implementer",
            prompt="wire up auth",
            verify_cmd="true",
            context_excerpts=["src/api/auth.py:45-89"],
        )
        assert step.context_excerpts == ["src/api/auth.py:45-89"]
        library = tmp_path / "library.yaml"
        library.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "catalog": [
                        {"name": "implementer", "type": "agent", "source": "x"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        plan = ExecutionPlan(
            goal="g",
            constitution_ref="CONSTITUTION.md",
            steps=[step],
        )
        ExecutionPlanValidator.from_library(library).validate(plan)
    finally:
        os.chdir(original_cwd)
        set_active_roster(prior)


def test_taskstep_spec_refs_accepts_existing_file(tmp_path: Path) -> None:
    """``spec_refs`` with an existing spec passes the full validator."""
    prior = get_active_roster()
    original_cwd = Path.cwd()
    import os

    try:
        set_active_roster({"implementer"})
        os.chdir(tmp_path)
        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()
        (spec_dir / "prompt-library-2026-04-14.md").write_text(
            "# spec\n", encoding="utf-8"
        )
        library = tmp_path / "library.yaml"
        library.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "catalog": [
                        {"name": "implementer", "type": "agent", "source": "x"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        plan = ExecutionPlan(
            goal="g",
            constitution_ref="CONSTITUTION.md",
            steps=[
                TaskStep(
                    id="S1",
                    agent="implementer",
                    prompt="implement",
                    verify_cmd="true",
                    spec_refs=["specs/prompt-library-2026-04-14.md"],
                )
            ],
        )
        ExecutionPlanValidator.from_library(library).validate(plan)
    finally:
        os.chdir(original_cwd)
        set_active_roster(prior)


def test_taskstep_spec_refs_missing_file_fails(tmp_path: Path) -> None:
    """``ExecutionPlanValidator.validate`` rejects missing ``spec_refs``."""
    prior = get_active_roster()
    original_cwd = Path.cwd()
    import os

    try:
        set_active_roster({"implementer"})
        os.chdir(tmp_path)
        library = tmp_path / "library.yaml"
        library.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "catalog": [
                        {"name": "implementer", "type": "agent", "source": "x"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        plan = ExecutionPlan(
            goal="g",
            constitution_ref="CONSTITUTION.md",
            steps=[
                TaskStep(
                    id="S1",
                    agent="implementer",
                    prompt="implement",
                    verify_cmd="true",
                    spec_refs=["specs/does-not-exist.md"],
                )
            ],
        )
        with pytest.raises(ValueError, match="references missing path"):
            ExecutionPlanValidator.from_library(library).validate(plan)
    finally:
        os.chdir(original_cwd)
        set_active_roster(prior)


def test_taskstep_agent_field_validator_accepts_context_roster() -> None:
    """Per-call ``context={"roster": {...}}`` overrides the module-level roster."""
    prior = get_active_roster()
    try:
        set_active_roster(set())  # no module-level roster
        # Without a roster, validator defers — both names accepted.
        TaskStep.model_validate(
            {
                "id": "S1",
                "agent": "anything",
                "prompt": "x",
                "verify_cmd": "true",
            }
        )
        # With an explicit roster, unknown agent is rejected.
        with pytest.raises(ValidationError, match="not in the roster"):
            TaskStep.model_validate(
                {
                    "id": "S1",
                    "agent": "anything",
                    "prompt": "x",
                    "verify_cmd": "true",
                },
                context={"roster": {"implementer", "verifier"}},
            )
    finally:
        set_active_roster(prior)


# ---------------------------------------------------------------------------
# ExecutionPlan.regression_baseline_cmd + compliance_flags (iter-2 γ1)
# ---------------------------------------------------------------------------


def test_regression_baseline_cmd_defaults_to_none() -> None:
    """Default is ``None``: only brownfield plans opt in explicitly."""
    prior = get_active_roster()
    try:
        set_active_roster({"implementer"})
        plan = ExecutionPlan(
            goal="g",
            constitution_ref="CONSTITUTION.md",
            steps=[
                TaskStep(
                    id="S1",
                    agent="implementer",
                    prompt="p",
                    verify_cmd="true",
                )
            ],
        )
        assert plan.regression_baseline_cmd is None
        assert plan.regression_baseline_timeout_sec == 120
        assert plan.compliance_flags == []
    finally:
        set_active_roster(prior)


def test_regression_baseline_cmd_accepts_allowlisted_cmd() -> None:
    """Commands whose argv[0] is on the allowlist pass the field validator."""
    prior = get_active_roster()
    try:
        set_active_roster({"implementer"})
        plan = ExecutionPlan(
            goal="g",
            constitution_ref="CONSTITUTION.md",
            regression_baseline_cmd="pytest --co -q",
            steps=[
                TaskStep(
                    id="S1",
                    agent="implementer",
                    prompt="p",
                    verify_cmd="true",
                )
            ],
        )
        assert plan.regression_baseline_cmd == "pytest --co -q"
    finally:
        set_active_roster(prior)


def test_regression_baseline_cmd_rejects_non_allowlisted() -> None:
    """Off-list argv[0] (``curl``, ``bash``) is rejected at parse time."""
    prior = get_active_roster()
    try:
        set_active_roster({"implementer"})
        with pytest.raises(ValidationError, match="allowlist"):
            ExecutionPlan(
                goal="g",
                constitution_ref="CONSTITUTION.md",
                regression_baseline_cmd="curl http://attacker.example",
                steps=[
                    TaskStep(
                        id="S1",
                        agent="implementer",
                        prompt="p",
                        verify_cmd="true",
                    )
                ],
            )
    finally:
        set_active_roster(prior)


def test_regression_baseline_cmd_rejects_empty_string() -> None:
    """Empty string is rejected; use ``None`` to opt out."""
    prior = get_active_roster()
    try:
        set_active_roster({"implementer"})
        with pytest.raises(ValidationError, match="non-empty"):
            ExecutionPlan(
                goal="g",
                constitution_ref="CONSTITUTION.md",
                regression_baseline_cmd="   ",
                steps=[
                    TaskStep(
                        id="S1",
                        agent="implementer",
                        prompt="p",
                        verify_cmd="true",
                    )
                ],
            )
    finally:
        set_active_roster(prior)


def test_regression_baseline_timeout_sec_bounds() -> None:
    """Timeout must fall in 1..600."""
    prior = get_active_roster()
    try:
        set_active_roster({"implementer"})
        with pytest.raises(ValidationError):
            ExecutionPlan(
                goal="g",
                constitution_ref="CONSTITUTION.md",
                regression_baseline_timeout_sec=0,
                steps=[
                    TaskStep(
                        id="S1",
                        agent="implementer",
                        prompt="p",
                        verify_cmd="true",
                    )
                ],
            )
        with pytest.raises(ValidationError):
            ExecutionPlan(
                goal="g",
                constitution_ref="CONSTITUTION.md",
                regression_baseline_timeout_sec=601,
                steps=[
                    TaskStep(
                        id="S1",
                        agent="implementer",
                        prompt="p",
                        verify_cmd="true",
                    )
                ],
            )
    finally:
        set_active_roster(prior)


def test_compliance_flags_normalise_to_lowercase_trimmed() -> None:
    """Tags are lowercased and trimmed; whitespace inside rejected."""
    prior = get_active_roster()
    try:
        set_active_roster({"implementer"})
        plan = ExecutionPlan(
            goal="g",
            constitution_ref="CONSTITUTION.md",
            compliance_flags=[" HIPAA ", "SOC2", "pci-dss"],
            steps=[
                TaskStep(
                    id="S1",
                    agent="implementer",
                    prompt="p",
                    verify_cmd="true",
                )
            ],
        )
        assert plan.compliance_flags == ["hipaa", "soc2", "pci-dss"]

        with pytest.raises(ValidationError, match="non-empty"):
            ExecutionPlan(
                goal="g",
                constitution_ref="CONSTITUTION.md",
                compliance_flags=["hipaa", ""],
                steps=[
                    TaskStep(
                        id="S1",
                        agent="implementer",
                        prompt="p",
                        verify_cmd="true",
                    )
                ],
            )
        with pytest.raises(ValidationError, match="whitespace"):
            ExecutionPlan(
                goal="g",
                constitution_ref="CONSTITUTION.md",
                compliance_flags=["pci dss"],
                steps=[
                    TaskStep(
                        id="S1",
                        agent="implementer",
                        prompt="p",
                        verify_cmd="true",
                    )
                ],
            )
    finally:
        set_active_roster(prior)


# ---------------------------------------------------------------------------
# QAReport
# ---------------------------------------------------------------------------


def test_qa_approve_clean_run() -> None:
    v = QAReport.verdict_from_findings([], TestResults(passed=5, coverage=0.9))
    assert v == "APPROVE"


def test_qa_block_on_failing_test() -> None:
    v = QAReport.verdict_from_findings(
        [], TestResults(passed=4, failed=1, coverage=0.9)
    )
    assert v == "BLOCK"


def test_qa_block_on_critical_security_finding() -> None:
    f = Finding(
        severity="critical",
        category="security",
        file="app.py",
        message="eval() on user input",
    )
    v = QAReport.verdict_from_findings([f], TestResults(coverage=0.9))
    assert v == "BLOCK"


def test_qa_block_on_three_critical_correctness() -> None:
    fs = [
        Finding(
            severity="critical",
            category="correctness",
            file="a.py",
            message=f"bug {i}",
        )
        for i in range(3)
    ]
    v = QAReport.verdict_from_findings(fs, TestResults(coverage=0.9))
    assert v == "BLOCK"


def test_qa_needs_attention_on_low_coverage() -> None:
    v = QAReport.verdict_from_findings([], TestResults(coverage=0.5))
    assert v == "NEEDS_ATTENTION"


def test_qa_report_roundtrip_json() -> None:
    r = QAReport(
        verdict="APPROVE",
        findings=[
            Finding(severity="low", category="style", file="a.py", message="nit"),
        ],
        test_results=TestResults(passed=10, coverage=0.91),
    )
    again = QAReport.model_validate_json(r.model_dump_json())
    assert again == r


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------


def test_spec_accepts_ears_shape() -> None:
    s = Spec(
        id="feat-001-ping",
        title="Ping endpoint",
        intent="Operators need a cheap liveness check.",
        outcomes=["Operators can curl /ping and get 200."],
        requirements=["The system shall return HTTP 200 from GET /ping."],
        acceptance_criteria=["curl -sf localhost/ping returns 200"],
    )
    assert s.version == "0.1.0"


def test_spec_rejects_non_ears_requirement() -> None:
    with pytest.raises(ValidationError):
        Spec(
            id="feat-002",
            title="bad",
            intent="i",
            outcomes=["o"],
            requirements=["Implement the thing."],  # no EARS trigger
            acceptance_criteria=["c"],
        )


def test_spec_bump_version() -> None:
    s = Spec(
        id="feat-003",
        title="t",
        intent="i",
        outcomes=["o"],
        requirements=["The system shall do X."],
        acceptance_criteria=["c"],
    )
    assert s.bump_version("minor").version == "0.2.0"
    assert s.bump_version("major").version == "1.0.0"


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------


def test_task_default_status() -> None:
    t = Task(id="T-1", title="Do thing", verify_cmd="true")
    assert t.status == "pending"


def test_task_mark_returns_copy() -> None:
    t = Task(id="T-1", title="Do thing", verify_cmd="true")
    t2 = t.mark("done")
    assert t.status == "pending"
    assert t2.status == "done"


def test_task_rejects_empty_verify_cmd() -> None:
    with pytest.raises(ValidationError):
        Task(id="T-2", title="x", verify_cmd="")


# ---------------------------------------------------------------------------
# AgentLogEntry
# ---------------------------------------------------------------------------


def test_agent_log_jsonl_has_trailing_newline() -> None:
    entry = AgentLogEntry(
        session_id="impl-abc", agent="implementer", action="Edit"
    )
    line = entry.to_jsonl()
    assert line.endswith("\n")
    assert '"session_id":"impl-abc"' in line


def test_agent_log_defaults_are_valid() -> None:
    entry = AgentLogEntry(
        session_id="s", agent="a", action="Bash", duration_ms=12
    )
    assert entry.status == "started"
    assert entry.cost_estimate == 0.0


def test_agent_log_rejects_bad_status() -> None:
    with pytest.raises(ValidationError):
        AgentLogEntry(
            session_id="s",
            agent="a",
            action="Bash",
            status="exploded",  # type: ignore[arg-type]
        )


# iter-3 ε1: wave-tree threading on AgentLogEntry --------------------------


def test_agent_log_wave_tree_fields_default_to_none() -> None:
    """ε1: parent_session_id, root_run_id, wave_idx, step_id default to None."""
    entry = AgentLogEntry(session_id="s", agent="a", action="Bash")
    assert entry.parent_session_id is None
    assert entry.root_run_id is None
    assert entry.wave_idx is None
    assert entry.step_id is None


def test_agent_log_wave_tree_fields_validate() -> None:
    """ε1: wave-tree fields accept their declared types end-to-end."""
    entry = AgentLogEntry(
        session_id="impl-abc",
        agent="implementer",
        action="Edit",
        parent_session_id="orchestrator-root",
        root_run_id="run-2026-04-14-001",
        wave_idx=2,
        step_id="S5",
    )
    assert entry.parent_session_id == "orchestrator-root"
    assert entry.root_run_id == "run-2026-04-14-001"
    assert entry.wave_idx == 2
    assert entry.step_id == "S5"
    # Round-trip through JSONL preserves the new fields.
    line = entry.to_jsonl()
    assert '"parent_session_id":"orchestrator-root"' in line
    assert '"wave_idx":2' in line
    assert '"step_id":"S5"' in line


def test_agent_log_wave_idx_must_be_non_negative() -> None:
    """ε1: wave_idx is 0-based; negatives are rejected."""
    with pytest.raises(ValidationError):
        AgentLogEntry(
            session_id="s",
            agent="a",
            action="Bash",
            wave_idx=-1,
        )
