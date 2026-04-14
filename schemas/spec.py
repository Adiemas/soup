"""Spec schema — output of the ``/specify`` command.

Per CONSTITUTION Article I, every feature starts with an EARS-style spec in
``specs/``. Specs describe *what* and *outcomes*, never *how*. Approved specs
are frozen; changes require a new version.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# EARS sentinel phrasing — "The system shall ..." family.
_EARS_PATTERN = re.compile(
    r"^\s*(the\s+system\s+shall|when\s+|while\s+|if\s+|where\s+).+",
    re.IGNORECASE,
)


class Spec(BaseModel):
    """User-facing spec document.

    Attributes:
        id: Stable identifier (slug, e.g. ``"feat-001-rag-ingest"``).
        title: Short human-readable title.
        intent: One-paragraph statement of *why*.
        outcomes: Observable behaviors the user gets once shipped.
        requirements: EARS-style "The system shall ..." / "When ..." clauses.
        acceptance_criteria: Binary pass/fail checks the verifier will run.
        frozen: True once approved; Pydantic does not enforce mutation freeze
            (callers must treat as immutable).
        version: Semantic version; bumps on any approved edit.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(..., pattern=r"^[a-z0-9][a-z0-9\-]*$")
    title: str = Field(..., min_length=1, max_length=120)
    intent: str = Field(..., min_length=1)
    outcomes: list[str] = Field(..., min_length=1)
    requirements: list[str] = Field(..., min_length=1)
    acceptance_criteria: list[str] = Field(..., min_length=1)
    frozen: bool = False
    version: str = Field(default="0.1.0", pattern=r"^\d+\.\d+\.\d+$")

    @field_validator("requirements")
    @classmethod
    def _ears_shape(cls, v: list[str]) -> list[str]:
        """Each requirement must match an EARS trigger keyword."""
        bad = [r for r in v if not _EARS_PATTERN.match(r)]
        if bad:
            raise ValueError(
                "requirements must start with EARS keyword "
                "('The system shall', 'When', 'While', 'If', 'Where'); "
                f"offending entries: {bad[:3]}"
            )
        return v

    def bump_version(self, part: str = "patch") -> Spec:
        """Return a copy with ``version`` incremented.

        ``part`` is one of ``"major"``, ``"minor"``, ``"patch"``.
        """
        major, minor, patch = (int(p) for p in self.version.split("."))
        if part == "major":
            major, minor, patch = major + 1, 0, 0
        elif part == "minor":
            minor, patch = minor + 1, 0
        elif part == "patch":
            patch += 1
        else:
            raise ValueError(f"unknown part {part!r}")
        return self.model_copy(update={"version": f"{major}.{minor}.{patch}"})

    def model_post_init(self, __context: Any) -> None:
        """No-op hook kept for parity with Pydantic conventions."""
        return None


__all__ = ["Spec"]
