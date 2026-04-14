"""Task schema — the ``/tasks`` output and per-step execution record.

A Task is the intermediate representation between a Spec/Plan and an
ExecutionPlan step. Tasks are TDD-shaped (one behavior, one failing test
first) per CONSTITUTION Article III.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TaskStatus = Literal["pending", "in_progress", "blocked", "done", "failed"]


class Task(BaseModel):
    """A single actionable unit of work.

    Attributes:
        id: Stable identifier (e.g. ``"T-007"``).
        title: Short imperative description ("Add ingest handler for GitHub").
        files: Files the task will touch (information; ``files_allowed`` on
            the matching TaskStep is the enforced scope).
        status: Lifecycle state; transitions are ``pending → in_progress →
            (done | failed | blocked)``.
        verify_cmd: Bash command run after implementation; exit 0 = pass.
        notes: Freeform author notes (rationale, TODOs, follow-ups).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(..., min_length=1, max_length=32)
    title: str = Field(..., min_length=1, max_length=200)
    files: list[str] = Field(default_factory=list)
    status: TaskStatus = "pending"
    verify_cmd: str = Field(..., min_length=1)
    notes: str = ""

    def mark(self, status: TaskStatus) -> Task:
        """Return a new Task with the updated status."""
        return self.model_copy(update={"status": status})


__all__ = ["Task", "TaskStatus"]
