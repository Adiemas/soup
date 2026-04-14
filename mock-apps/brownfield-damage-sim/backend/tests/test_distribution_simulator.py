"""RED-phase tests driving S1 / S4 of .soup/plan.json.

These tests FAIL today for the right reason (missing behaviour), not because
of syntax errors or bad imports. They are the specification, expressed as
code, per CONSTITUTION Article III.1.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

# Intentionally imported from the (fake) target repo path so the test reads
# like it would in the real integration. In the mock-app these modules don't
# exist yet — the RED failure mode is ImportError, which is the right
# failure: "the module is missing because the feature is missing."
from backend.src.damage_sim.calculator import (  # noqa: F401  # missing -> RED
    EnhancedCombatCalculator,
)


# Canonical scenario — matches the Space Marine vs Ork Boy example cited in
# the existing repo's CLAUDE.md ("Combat calculator end-to-end tested").
CANONICAL_SCENARIO: dict[str, Any] = {
    "attacker_unit": {
        "name": "Space Marine",
        "weapon_skill": 3,
        "ballistic_skill": 3,
    },
    "attacker_weapon": {
        "name": "Bolt Rifle",
        "attacks": 2,
        "strength": 4,
        "armor_penetration": 0,
        "damage": 1,
    },
    "defender_unit": {
        "name": "Ork Boy",
        "toughness": 4,
        "save": 6,
        "wounds": 1,
    },
    "attack_count": 10,
    "iterations": 1000,
}

# Committed pre-change hash of /calculate response on this scenario. If this
# test fails, the "byte-for-byte preserved" acceptance criterion (AC-2) has
# been violated — STOP and diagnose before proceeding.
EXPECTED_CALCULATE_RESPONSE_HASH = "CHARACTERIZATION_HASH_SENTINEL"


class TestPreservedCalculateSurface:
    """AC-2: POST /calculate response bytes on the canonical scenario equal
    the pre-change baseline. This is a characterization test — it guards the
    existing surface against silent drift while we add a NEW sibling route.
    """

    def test_calculate_response_hash_unchanged(self, test_client: Any) -> None:
        """Fails today because no baseline hash exists yet; fails post-change
        if the handler was edited (brownfield violation)."""
        resp = test_client.post("/api/v1/calculate/calculate",
                                json=CANONICAL_SCENARIO)
        assert resp.status_code == 200
        canonical_bytes = json.dumps(resp.json(), sort_keys=True).encode()
        actual_hash = hashlib.sha256(canonical_bytes).hexdigest()
        assert actual_hash == EXPECTED_CALCULATE_RESPONSE_HASH, (
            "POST /calculate response bytes drifted — brownfield violation. "
            "Per spec AC-2, the existing surface is preserved byte-for-byte. "
            f"Expected {EXPECTED_CALCULATE_RESPONSE_HASH}, got {actual_hash}."
        )


class TestSimulateDistributionNewSurface:
    """AC-1, FR-1, FR-2, FR-3: new endpoint returns full distribution."""

    def test_simulate_distribution_returns_full_shape(self) -> None:
        calc = EnhancedCombatCalculator(iterations=1000)
        # This method does not exist yet — RED phase for S4.
        result = calc.simulate_distribution(
            scenario=CANONICAL_SCENARIO,
            seed=42,
        )
        # Shape check (FR-2):
        assert set(result.keys()) >= {
            "distribution",
            "percentiles",
            "mean",
            "variance",
            "iterations_run",
        }
        assert isinstance(result["distribution"], dict)
        assert set(result["percentiles"].keys()) == {"p50", "p90", "p99"}
        assert result["iterations_run"] == 1000
        # Probabilities sum to ~1 (allow monte-carlo float drift).
        total_p = sum(result["distribution"].values())
        assert abs(total_p - 1.0) < 1e-6, (
            f"Distribution probabilities must sum to 1; got {total_p}"
        )

    def test_simulate_distribution_is_deterministic_with_seed(self) -> None:
        """Seed reproducibility — without this, regression-tests flake."""
        calc = EnhancedCombatCalculator(iterations=1000)
        a = calc.simulate_distribution(scenario=CANONICAL_SCENARIO, seed=42)
        b = calc.simulate_distribution(scenario=CANONICAL_SCENARIO, seed=42)
        assert a == b, "Seeded simulation must be deterministic."


@pytest.fixture
def test_client() -> Any:
    """FastAPI TestClient against the wired-up app. Intentionally left
    unimplemented in the mock-app; the real plan mounts the existing app."""
    pytest.skip("Wire to real app.main:app in the target repo.")
