"""Intake form schema — input to the ``/intake`` command.

Streck engineers start new internal apps from a structured **intake
form**, not a free-text goal. The form is filled in YAML, validated by
:class:`IntakeForm`, and consumed by ``spec-writer`` to produce a
first-class spec under ``specs/<app_slug>-<date>.md``.

See ``intake/README.md`` for the operator-facing field reference and
``.claude/commands/intake.md`` for the workflow.
"""

from __future__ import annotations

import re
import warnings
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ----- Field types --------------------------------------------------------

_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

StackPreference = Literal[
    "python-fastapi-postgres",
    "dotnet-webapi-postgres",
    "react-ts-vite",
    "fullstack-python-react",
    "nextjs-app-router",
    "ts-node-script",
    "no-preference",
]

DeploymentTarget = Literal[
    "internal-docker",
    "azure",
    "vercel",
    "on-prem",
    "tbd",
]

ComplianceFlag = Literal[
    "pii",
    "phi",
    "financial",
    "lab-data",
    "public",
    "internal-only",
]

IntegrationKind = Literal[
    "github-repo",
    "ado-project",
    "rest-api",
    "graphql-api",
    "database",
    "sftp",
    "s3",
    "other",
]

IntegrationAuth = Literal["pat", "oauth", "api-key", "none", "tbd"]

IntakeFieldType = Literal["text", "number", "file", "image", "api-call", "other"]


# ----- Sub-models ---------------------------------------------------------


class IntakeField(BaseModel):
    """One input or output field of the proposed app.

    ``inputs`` and ``outputs`` use this same shape so that the spec-writer
    can render them symmetrically into Functional Requirements
    ("The system shall accept ..." vs "The system shall produce ...").
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=80)
    description: str = Field(..., min_length=1)
    type: IntakeFieldType


class Integration(BaseModel):
    """One external system this app reads from or writes to.

    ``ref`` is the locator (URL, ``org/repo``, ADO project name); the
    ``intake`` command surfaces these as `## Integrations` requirements
    and downstream as ``TaskStep.context_excerpts`` hints so the
    specialist subagents see the contract excerpt without re-discovering
    it.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: IntegrationKind
    ref: str = Field(..., min_length=1, max_length=200)
    purpose: str = Field(
        ...,
        min_length=1,
        description="What this app reads or writes against the integration.",
    )
    auth: IntegrationAuth


# ----- Top-level model ----------------------------------------------------


class IntakeForm(BaseModel):
    """Canonical intake form for a new Streck internal app.

    Attributes:
        app_slug: kebab-case identifier — drives ``specs/<slug>-...``,
            ``.soup/plans/<slug>...``, and the new-repo directory name.
        app_name: Human-readable name displayed in the UI / docs.
        description: 1-3 sentence elevator pitch.
        intent: User value + business driver (the "why").
        requesting_team: e.g. ``"Lab Ops"``, ``"Compliance"``.
        primary_users: Persona names (e.g. ``"Lab Tech"``, ``"QA Lead"``).
        inputs: Inbound data — user, system, source-of-record fields.
        outputs: Outbound surfaces — UI views, reports, APIs, exports.
        integrations: External systems consumed or produced.
        stack_preference: One of the canonical ``/soup-init`` templates,
            or ``no-preference`` to let the architect choose.
        deployment_target: Where the app will run.
        success_outcomes: Testable statements ("90% of pipettes show
            calibration status within 5s").
        constraints: Regulatory, performance, budget caps.
        deadline: ISO date or ``None`` (e.g. ``"2026-06-14"``).
        compliance_flags: Domain compliance markers — drive rule
            injection (PII/PHI/financial → security-scanner severity
            uplift; lab-data → audit log requirement).
        deploy_baseline_cmd: Optional deployment-target smoke command,
            symmetrical to ``ExecutionPlan.regression_baseline_cmd``.
            The ``deployer`` agent runs it pre- and post-deploy
            against the remote target; any regression in the response
            set blocks merge.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    app_slug: str = Field(..., min_length=2, max_length=64)
    app_name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(..., min_length=1)
    intent: str = Field(..., min_length=1)
    requesting_team: str = Field(..., min_length=1, max_length=80)
    primary_users: list[str] = Field(..., min_length=1)
    inputs: list[IntakeField] = Field(..., min_length=1)
    outputs: list[IntakeField] = Field(..., min_length=1)
    integrations: list[Integration] = Field(default_factory=list)
    stack_preference: StackPreference
    deployment_target: DeploymentTarget
    success_outcomes: list[str] = Field(..., min_length=1)
    constraints: list[str] = Field(default_factory=list)
    deadline: str | None = Field(default=None)
    compliance_flags: list[ComplianceFlag] = Field(default_factory=list)
    deploy_baseline_cmd: str | None = Field(default=None)

    # ----- Validators ---------------------------------------------------

    @field_validator("app_slug")
    @classmethod
    def _slug_shape(cls, v: str) -> str:
        """Reject non-kebab-case slugs.

        ``app_slug`` becomes a path segment in ``specs/``, ``.soup/plans/``,
        and the sibling app directory under ``SOUP_APPS_DIR``. We restrict
        to ``[a-z0-9-]`` starting with a letter so paths stay portable
        (Windows/macOS/Linux), URL-safe, and unambiguous.
        """
        if not _SLUG_PATTERN.match(v):
            raise ValueError(
                f"app_slug {v!r} must be kebab-case "
                "(lowercase letters/digits with hyphens, starting with a letter; "
                "e.g. 'pipette-calibration-dashboard')"
            )
        return v

    @field_validator("deadline")
    @classmethod
    def _deadline_is_iso_date(cls, v: str | None) -> str | None:
        """Reject deadlines that are not ISO 8601 dates (``YYYY-MM-DD``)."""
        if v is None:
            return v
        if not _DATE_PATTERN.match(v):
            raise ValueError(
                f"deadline {v!r} must be ISO date YYYY-MM-DD or null"
            )
        # Round-trip through ``date.fromisoformat`` to reject e.g. 2026-13-40.
        try:
            date.fromisoformat(v)
        except ValueError as exc:
            raise ValueError(f"deadline {v!r} is not a valid calendar date") from exc
        return v

    @field_validator("compliance_flags")
    @classmethod
    def _flags_are_unique(cls, v: list[ComplianceFlag]) -> list[ComplianceFlag]:
        if len(set(v)) != len(v):
            dupes = sorted({f for f in v if v.count(f) > 1})
            raise ValueError(f"duplicate compliance_flags: {dupes}")
        return v

    @model_validator(mode="after")
    def _flags_are_consistent(self) -> IntakeForm:
        """Cross-field consistency between ``compliance_flags`` and
        ``deployment_target``.

        Rules (each a hard ``ValueError`` unless stated otherwise):

        - ``public`` is mutually exclusive with ``internal-only``, ``pii``,
          ``phi``, and ``financial``. Catches the common intake mistake
          of ticking both ``public`` and a sensitive-data flag. Lab data
          is fine alongside ``internal-only``.
        - ``internal-only`` + ``deployment_target == "vercel"`` → reject.
          Vercel is a public-edge platform; use ``on-prem`` or
          ``azure`` (with private endpoint) for internal-only apps.
        - ``phi`` + ``deployment_target == "vercel"`` → reject. PHI
          requires BAA'd infrastructure; Vercel does not sign BAAs by
          default.
        - ``deployment_target == "tbd"`` with no ``constraints`` entry
          mentioning "deploy TBD" → advisory warning (not error) via
          ``warnings.warn``. The deployer will still refuse at deploy
          time, but the warning prompts the intake author to record
          the reason the target is unresolved so downstream planning
          can factor it in.
        """
        flags = set(self.compliance_flags)
        if "public" in flags and flags & {
            "internal-only",
            "pii",
            "phi",
            "financial",
        }:
            raise ValueError(
                "compliance_flags: 'public' is mutually exclusive with "
                "'internal-only', 'pii', 'phi', and 'financial'"
            )
        if "internal-only" in flags and self.deployment_target == "vercel":
            raise ValueError(
                "compliance_flags/deployment_target: Vercel is "
                "public-edge; use on-prem or azure for internal-only"
            )
        if "phi" in flags and self.deployment_target == "vercel":
            raise ValueError(
                "compliance_flags/deployment_target: PHI requires BAA'd "
                "infra; Vercel doesn't sign BAAs by default"
            )
        if self.deployment_target == "tbd":
            mentions_tbd = any(
                "deploy tbd" in c.lower() for c in self.constraints
            )
            if not mentions_tbd:
                warnings.warn(
                    "deployment_target is 'tbd' but no constraints entry "
                    "mentions 'deploy TBD'; record the reason the target "
                    "is unresolved so /plan can route around it.",
                    stacklevel=2,
                )
        return self

    # ----- Constructors -------------------------------------------------

    @classmethod
    def from_yaml(cls, path: str | Path) -> IntakeForm:
        """Load and validate an intake form from a YAML file on disk.

        Raises:
            FileNotFoundError: ``path`` does not exist.
            ValueError: YAML parse error or schema validation failure.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"intake form not found: {p}")
        try:
            raw: Any = yaml.safe_load(p.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ValueError(f"intake form {p}: invalid YAML — {exc}") from exc
        if not isinstance(raw, dict):
            raise ValueError(
                f"intake form {p}: top-level must be a mapping, got {type(raw).__name__}"
            )
        return cls.model_validate(raw)


__all__ = [
    "ComplianceFlag",
    "DeploymentTarget",
    "IntakeField",
    "IntakeFieldType",
    "IntakeForm",
    "Integration",
    "IntegrationAuth",
    "IntegrationKind",
    "StackPreference",
]
