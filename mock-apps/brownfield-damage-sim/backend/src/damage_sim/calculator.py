"""Minimal impl sketch for S4 — NOT the real feature.

This file exists to exercise the TDD scaffolding end-to-end in the
mock-app. A production implementation would:

1. Import the real ``EnhancedCombatCalculator`` from
   ``backend/app/services/combat_calculator.py`` of the warhammer repo
   (specifically the ``_calculate_damage_distribution`` private method at
   line ~418, which already runs a 10k-iteration Monte Carlo loop and
   returns ``{damage: count}``).
2. Add a public ``simulate_distribution`` that wraps it with percentile
   computation, variance, and a seeded RNG.
3. Apply ExternalBalance modifiers to ``scenario.modifiers`` BEFORE
   entering the loop — not inside it — so the modifier math stays
   identical to ``/calculate``.

The shim below is ONLY enough for a test-engineer to verify the test
harness can import it and drive a failing assertion about percentiles.
"""
from __future__ import annotations

import random
import statistics
from collections import Counter
from typing import Any


class EnhancedCombatCalculator:
    """Shim — real impl lives in
    ``backend/app/services/combat_calculator.py`` of the target repo."""

    def __init__(self, iterations: int = 10_000) -> None:
        self.iterations = iterations

    def simulate_distribution(
        self,
        scenario: dict[str, Any],
        seed: int | None = None,
    ) -> dict[str, Any]:
        """Return the full damage distribution for one scenario run.

        This is a TOY implementation — it deliberately under-specifies the
        damage math so the test can be driven against it. The real
        implementation reuses the existing ``_calculate_damage_distribution``
        loop rather than reimplementing it.
        """
        rng = random.Random(seed)
        attacks = scenario["attack_count"]
        damage_per_hit = scenario["attacker_weapon"]["damage"]
        hit_target = scenario["attacker_unit"]["weapon_skill"]

        samples: list[int] = []
        for _ in range(self.iterations):
            rolls = [rng.randint(1, 6) for _ in range(attacks)]
            damage = sum(damage_per_hit for r in rolls if r >= hit_target)
            samples.append(damage)

        counts = Counter(samples)
        distribution = {
            int(k): v / self.iterations for k, v in counts.items()
        }
        sorted_samples = sorted(samples)

        def pct(p: float) -> float:
            idx = max(0, min(len(sorted_samples) - 1,
                             int(round(p * (len(sorted_samples) - 1)))))
            return float(sorted_samples[idx])

        return {
            "distribution": distribution,
            "percentiles": {
                "p50": pct(0.50),
                "p90": pct(0.90),
                "p99": pct(0.99),
            },
            "mean": statistics.fmean(samples),
            "variance": statistics.pvariance(samples),
            "iterations_run": self.iterations,
        }
