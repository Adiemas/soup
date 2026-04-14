"""Soup schemas — Pydantic v2 data contracts.

Re-exports the public types used by the orchestrator, hooks, and CLI.
See ``docs/DESIGN.md`` §3 for the contract definitions.
"""

from __future__ import annotations

from schemas.agent_log import AgentLogEntry, LogStatus
from schemas.execution_plan import (
    ExecutionPlan,
    ExecutionPlanValidator,
    ModelTier,
    TaskStep,
    load_agent_roster,
)
from schemas.qa_report import (
    Category,
    Finding,
    QAReport,
    Severity,
    TestResults,
    Verdict,
)
from schemas.spec import Spec
from schemas.task import Task, TaskStatus

__all__ = [
    "AgentLogEntry",
    "Category",
    "ExecutionPlan",
    "ExecutionPlanValidator",
    "Finding",
    "LogStatus",
    "ModelTier",
    "QAReport",
    "Severity",
    "Spec",
    "Task",
    "TaskStatus",
    "TaskStep",
    "TestResults",
    "Verdict",
    "load_agent_roster",
]
