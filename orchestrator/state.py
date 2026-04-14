"""JSON-backed per-run state.

Each ``soup run`` gets a UUID and a state file at ``.soup/runs/<run_id>.json``.
The orchestrator persists after every step so a crashed/aborted run can be
inspected (and, later, resumed).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

StepStatus = Literal[
    "pending", "running", "passed", "failed", "skipped", "debugging"
]


class StepRecord(BaseModel):
    """Per-step execution record."""

    model_config = ConfigDict(extra="forbid")

    id: str
    agent: str
    status: StepStatus = "pending"
    wave: int = -1
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int = 0
    verify_exit: int | None = None
    output_path: str | None = None
    notes: str = ""


class RunState(BaseModel):
    """Top-level run container persisted as JSON.

    Use :meth:`new` to create, :meth:`load` to reload from disk, and
    :meth:`save` to flush after mutations.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    goal: str
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )
    finished_at: datetime | None = None
    status: Literal[
        "running", "passed", "failed", "aborted", "regression"
    ] = "running"
    steps: dict[str, StepRecord] = Field(default_factory=dict)
    budget_sec: int = 3600
    regression_baseline_diff_path: str | None = Field(
        default=None,
        description=(
            "Path to the post-run diff between ``pre.txt`` and "
            "``post.txt`` under ``.soup/baseline/<run_id>/`` when the "
            "plan declared ``regression_baseline_cmd``. ``None`` if the "
            "plan did not request baseline capture or the post-run leg "
            "was skipped (e.g. orchestrator aborted before completion)."
        ),
    )
    _path: Path | None = None

    # --- construction ---------------------------------------------------
    @classmethod
    def new(
        cls, goal: str, budget_sec: int, runs_dir: str | Path
    ) -> RunState:
        """Create a new run and its state file."""
        st = cls(goal=goal, budget_sec=budget_sec)
        st._path = Path(runs_dir) / f"{st.run_id}.json"
        st._path.parent.mkdir(parents=True, exist_ok=True)
        st.save()
        return st

    @classmethod
    def load(cls, path: str | Path) -> RunState:
        """Load an existing run-state JSON file."""
        p = Path(path)
        data: Any = json.loads(p.read_text(encoding="utf-8"))
        st = cls.model_validate(data)
        st._path = p
        return st

    # --- mutation -------------------------------------------------------
    def upsert_step(self, rec: StepRecord) -> None:
        """Insert or update a step record; does not save to disk."""
        self.steps[rec.id] = rec

    def save(self) -> None:
        """Write the state to its backing file atomically."""
        if self._path is None:
            raise RuntimeError("RunState has no backing path; use new()/load()")
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(self._path)

    @property
    def path(self) -> Path | None:
        """Backing JSON path, if any."""
        return self._path


__all__ = ["RunState", "StepRecord", "StepStatus"]
