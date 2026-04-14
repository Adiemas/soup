"""QA report schemas — the Stop-hook qa-orchestrator contract.

Per DESIGN.md §3 and CONSTITUTION Article IV, the Stop hook dispatches
code-reviewer, security-scanner, and verifier in parallel, then synthesizes
their findings into a single ``QAReport``. The verdict is computed by
deterministic blocking rules, not by LLM judgment.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Severity = Literal["critical", "high", "medium", "low"]
Category = Literal["security", "correctness", "style", "test", "coverage"]
Verdict = Literal["APPROVE", "NEEDS_ATTENTION", "BLOCK"]

# Blocking thresholds (DESIGN §3 + CONSTITUTION Article IV)
_CRITICAL_CORRECTNESS_BLOCK = 3
_COVERAGE_ATTENTION = 0.70
_MEDIUM_ATTENTION = 3


class Finding(BaseModel):
    """A single QA observation emitted by one of the scanners."""

    model_config = ConfigDict(extra="forbid")

    severity: Severity
    category: Category
    file: str = Field(..., min_length=1)
    line: int | None = Field(default=None, ge=0)
    message: str = Field(..., min_length=1)


class TestResults(BaseModel):
    """Aggregated test outcome counts plus coverage fraction."""

    # Tell pytest this is a data model, not a test class (starts with "Test").
    __test__ = False

    model_config = ConfigDict(extra="forbid")

    passed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)


class QAReport(BaseModel):
    """Synthesized output of the qa-orchestrator.

    The ``verdict`` is computed by :meth:`verdict_from_findings`; callers may
    also set it directly if they already derived it elsewhere.
    """

    model_config = ConfigDict(extra="forbid")

    verdict: Verdict
    findings: list[Finding] = Field(default_factory=list)
    test_results: TestResults = Field(default_factory=TestResults)

    @field_validator("verdict")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return v.upper()

    @classmethod
    def verdict_from_findings(
        cls,
        findings: list[Finding],
        test_results: TestResults,
    ) -> Verdict:
        """Apply blocking rules from DESIGN §3 and CONSTITUTION Article IV.

        Rules (evaluated in order):

        * BLOCK if ``test_results.failed > 0``.
        * BLOCK if any critical security finding exists.
        * BLOCK if ``critical`` correctness findings ``>= 3``.
        * NEEDS_ATTENTION if ``test_results.coverage < 0.70``.
        * NEEDS_ATTENTION if ``medium`` (any category) findings ``>= 3``.
        * Otherwise APPROVE.
        """
        if test_results.failed > 0:
            return "BLOCK"
        criticals = [f for f in findings if f.severity == "critical"]
        if any(f.category == "security" for f in criticals):
            return "BLOCK"
        critical_correctness = sum(
            1 for f in criticals if f.category == "correctness"
        )
        if critical_correctness >= _CRITICAL_CORRECTNESS_BLOCK:
            return "BLOCK"
        if test_results.coverage < _COVERAGE_ATTENTION:
            return "NEEDS_ATTENTION"
        mediums = sum(1 for f in findings if f.severity == "medium")
        if mediums >= _MEDIUM_ATTENTION:
            return "NEEDS_ATTENTION"
        return "APPROVE"


__all__ = [
    "Category",
    "Finding",
    "QAReport",
    "Severity",
    "TestResults",
    "Verdict",
]
