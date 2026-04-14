"""Unit tests for ``schemas/intake_form.py``."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from schemas.intake_form import IntakeField, IntakeForm, Integration

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _valid_intake_dict() -> dict[str, Any]:
    """Return a minimally-valid intake form payload."""
    return {
        "app_slug": "asset-inventory-lite",
        "app_name": "Asset Inventory Lite",
        "description": "Track lab assets in a single internal page.",
        "intent": "Lab Ops needs a single source of truth for asset locations.",
        "requesting_team": "Lab Ops",
        "primary_users": ["Lab Tech", "Lab Ops Manager"],
        "inputs": [
            {
                "name": "asset_id",
                "description": "Numeric asset tag scanned from the device.",
                "type": "number",
            }
        ],
        "outputs": [
            {
                "name": "asset_table",
                "description": "Sortable HTML table of assets.",
                "type": "other",
            }
        ],
        "integrations": [],
        "stack_preference": "python-fastapi-postgres",
        "deployment_target": "internal-docker",
        "success_outcomes": ["Lab Tech can find any asset in <30s."],
        "constraints": [],
        "deadline": None,
        "compliance_flags": ["internal-only"],
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_valid_intake_parses() -> None:
    form = IntakeForm.model_validate(_valid_intake_dict())
    assert form.app_slug == "asset-inventory-lite"
    assert form.stack_preference == "python-fastapi-postgres"
    assert form.compliance_flags == ["internal-only"]
    assert form.deadline is None
    assert form.integrations == []


def test_intake_round_trips_through_yaml(tmp_path: Path) -> None:
    payload = _valid_intake_dict()
    payload["integrations"] = [
        {
            "kind": "github-repo",
            "ref": "streck/asset-tracker",
            "purpose": "Pull asset metadata snapshot.",
            "auth": "pat",
        }
    ]
    p = tmp_path / "intake.yaml"
    p.write_text(yaml.safe_dump(payload), encoding="utf-8")
    form = IntakeForm.from_yaml(p)
    assert len(form.integrations) == 1
    assert isinstance(form.integrations[0], Integration)
    assert form.integrations[0].kind == "github-repo"


def test_intake_field_accepts_all_documented_types() -> None:
    for field_type in ("text", "number", "file", "image", "api-call", "other"):
        field = IntakeField(name="x", description="d", type=field_type)  # type: ignore[arg-type]
        assert field.type == field_type


# ---------------------------------------------------------------------------
# Missing-required errors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing",
    [
        "app_slug",
        "app_name",
        "description",
        "intent",
        "requesting_team",
        "primary_users",
        "inputs",
        "outputs",
        "stack_preference",
        "deployment_target",
        "success_outcomes",
    ],
)
def test_missing_required_field_raises(missing: str) -> None:
    payload = _valid_intake_dict()
    del payload[missing]
    with pytest.raises(ValidationError) as exc:
        IntakeForm.model_validate(payload)
    assert missing in str(exc.value)


def test_empty_primary_users_rejected() -> None:
    payload = _valid_intake_dict()
    payload["primary_users"] = []
    with pytest.raises(ValidationError):
        IntakeForm.model_validate(payload)


def test_empty_inputs_rejected() -> None:
    payload = _valid_intake_dict()
    payload["inputs"] = []
    with pytest.raises(ValidationError):
        IntakeForm.model_validate(payload)


def test_empty_outputs_rejected() -> None:
    payload = _valid_intake_dict()
    payload["outputs"] = []
    with pytest.raises(ValidationError):
        IntakeForm.model_validate(payload)


def test_empty_success_outcomes_rejected() -> None:
    payload = _valid_intake_dict()
    payload["success_outcomes"] = []
    with pytest.raises(ValidationError):
        IntakeForm.model_validate(payload)


# ---------------------------------------------------------------------------
# Bad app_slug shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_slug",
    [
        "Pipette-Calibration",  # uppercase
        "pipette_calibration",  # underscore
        "1pipette",  # leading digit
        "pipette--cal",  # double hyphen
        "-pipette",  # leading hyphen
        "pipette-",  # trailing hyphen
        "pipette cal",  # whitespace
        "p",  # too short (min_length=2)
    ],
)
def test_bad_app_slug_rejected(bad_slug: str) -> None:
    payload = _valid_intake_dict()
    payload["app_slug"] = bad_slug
    with pytest.raises(ValidationError) as exc:
        IntakeForm.model_validate(payload)
    msg = str(exc.value)
    # min_length violation reports as ``string_too_short`` rather than the
    # custom kebab-case message — accept either.
    assert "app_slug" in msg or "string_too_short" in msg


# ---------------------------------------------------------------------------
# Stack/deployment/compliance enums
# ---------------------------------------------------------------------------


def test_unknown_stack_rejected() -> None:
    payload = _valid_intake_dict()
    payload["stack_preference"] = "rust-axum"
    with pytest.raises(ValidationError):
        IntakeForm.model_validate(payload)


def test_unknown_deployment_target_rejected() -> None:
    payload = _valid_intake_dict()
    payload["deployment_target"] = "kubernetes"
    with pytest.raises(ValidationError):
        IntakeForm.model_validate(payload)


def test_no_preference_stack_accepted() -> None:
    payload = _valid_intake_dict()
    payload["stack_preference"] = "no-preference"
    form = IntakeForm.model_validate(payload)
    assert form.stack_preference == "no-preference"


def test_public_with_pii_is_rejected() -> None:
    payload = _valid_intake_dict()
    payload["compliance_flags"] = ["public", "pii"]
    with pytest.raises(ValidationError, match="mutually exclusive"):
        IntakeForm.model_validate(payload)


def test_public_with_internal_only_is_rejected() -> None:
    payload = _valid_intake_dict()
    payload["compliance_flags"] = ["public", "internal-only"]
    with pytest.raises(ValidationError, match="mutually exclusive"):
        IntakeForm.model_validate(payload)


def test_duplicate_compliance_flags_rejected() -> None:
    payload = _valid_intake_dict()
    payload["compliance_flags"] = ["internal-only", "internal-only"]
    with pytest.raises(ValidationError, match="duplicate compliance_flags"):
        IntakeForm.model_validate(payload)


# ---------------------------------------------------------------------------
# Deadline validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_deadline",
    ["2026/06/14", "06-14-2026", "next month", "2026-13-01", "2026-02-30"],
)
def test_bad_deadline_rejected(bad_deadline: str) -> None:
    payload = _valid_intake_dict()
    payload["deadline"] = bad_deadline
    with pytest.raises(ValidationError):
        IntakeForm.model_validate(payload)


def test_valid_deadline_accepted() -> None:
    payload = _valid_intake_dict()
    payload["deadline"] = "2026-06-14"
    form = IntakeForm.model_validate(payload)
    assert form.deadline == "2026-06-14"


# ---------------------------------------------------------------------------
# Integration validation
# ---------------------------------------------------------------------------


def test_unknown_integration_kind_rejected() -> None:
    payload = _valid_intake_dict()
    payload["integrations"] = [
        {
            "kind": "kafka",
            "ref": "cluster-1",
            "purpose": "p",
            "auth": "tbd",
        }
    ]
    with pytest.raises(ValidationError):
        IntakeForm.model_validate(payload)


def test_unknown_integration_auth_rejected() -> None:
    payload = _valid_intake_dict()
    payload["integrations"] = [
        {
            "kind": "rest-api",
            "ref": "https://api.example.com",
            "purpose": "p",
            "auth": "kerberos",
        }
    ]
    with pytest.raises(ValidationError):
        IntakeForm.model_validate(payload)


# ---------------------------------------------------------------------------
# from_yaml errors
# ---------------------------------------------------------------------------


def test_from_yaml_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        IntakeForm.from_yaml("does/not/exist.yaml")


def test_from_yaml_non_mapping_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    with pytest.raises(ValueError, match="top-level must be a mapping"):
        IntakeForm.from_yaml(p)


def test_from_yaml_invalid_yaml_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text(": : :\n  - oops\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid YAML"):
        IntakeForm.from_yaml(p)


def test_extra_fields_rejected() -> None:
    payload = _valid_intake_dict()
    payload["secret_field"] = "shhh"
    with pytest.raises(ValidationError):
        IntakeForm.model_validate(payload)


# ---------------------------------------------------------------------------
# Deployment target vs compliance-flag consistency (iter-3 δ)
# ---------------------------------------------------------------------------


def test_internal_only_plus_vercel_rejected() -> None:
    """Vercel is public-edge; internal-only apps must not target it."""
    payload = _valid_intake_dict()
    payload["deployment_target"] = "vercel"
    payload["compliance_flags"] = ["internal-only"]
    with pytest.raises(
        ValidationError, match=r"Vercel is public-edge.*internal-only"
    ):
        IntakeForm.model_validate(payload)


def test_phi_plus_vercel_rejected() -> None:
    """PHI requires BAA'd infra; Vercel does not sign BAAs by default."""
    payload = _valid_intake_dict()
    payload["deployment_target"] = "vercel"
    # PHI is not mutually exclusive with public (public + phi is a data
    # leak, but the earlier validator handles it). Use an intake that
    # carries phi alone so we exercise the PHI-vs-vercel branch.
    payload["compliance_flags"] = ["phi"]
    with pytest.raises(ValidationError, match=r"PHI requires BAA'd infra"):
        IntakeForm.model_validate(payload)


def test_deployment_target_tbd_without_constraint_warns() -> None:
    """``deployment_target: tbd`` without a ``deploy TBD`` constraint
    entry emits an advisory warning (not an error). The deployer
    still refuses at deploy time, but the warning prompts the intake
    author to record the reason.
    """
    payload = _valid_intake_dict()
    payload["deployment_target"] = "tbd"
    payload["constraints"] = ["must launch by Q3"]
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        form = IntakeForm.model_validate(payload)
        assert form.deployment_target == "tbd"
        assert any(
            "deployment_target is 'tbd'" in str(warning.message) for warning in w
        )

    # Control: with an explicit 'deploy TBD' constraint entry, no warning.
    payload["constraints"] = ["deploy TBD pending infra review"]
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        IntakeForm.model_validate(payload)
        assert not any(
            "deployment_target is 'tbd'" in str(warning.message) for warning in w
        )


def test_deploy_baseline_cmd_is_optional_and_stashed() -> None:
    """``deploy_baseline_cmd`` is optional; when set it survives
    model_validate and is available to the deployer agent.
    """
    payload = _valid_intake_dict()
    assert "deploy_baseline_cmd" not in payload
    form = IntakeForm.model_validate(payload)
    assert form.deploy_baseline_cmd is None

    payload["deploy_baseline_cmd"] = "curl -fsS $URL/api/endpoints"
    form = IntakeForm.model_validate(payload)
    assert form.deploy_baseline_cmd == "curl -fsS $URL/api/endpoints"
