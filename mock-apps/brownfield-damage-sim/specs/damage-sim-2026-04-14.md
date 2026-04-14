# Spec: Damage Simulator API (brownfield extension)

_Slug:_ `damage-sim` _Date:_ 2026-04-14
_Extends existing feature:_ `backend/app/api/calculations.py` (combat-calculator REST surface)
_Stakeholder ask:_ "Add a 'damage simulator' feature that exposes a REST API
accepting unit + target specs and returns Monte Carlo damage distribution. The
existing combat-calculator API must be extended, not forked. The simulator
also needs to call the ExternalBalance API (a mock external REST service) for
balance data."

## Summary

Extend the existing `calculations` router with a new POST endpoint that
returns the full Monte Carlo damage distribution (histogram, percentiles,
variance) for a weapon-vs-target scenario, enriched with live balance data
pulled from the ExternalBalance REST service. The existing `/calculate`
endpoint is preserved as-is; the new endpoint is additive.

## Stakeholders & personas

- **Competitive player** — wants the full distribution, not just a point
  estimate, to evaluate swing scenarios.
- **Back-end on-call** — owns the existing `/calculate` surface and must
  not see its P95 latency regress.
- **ExternalBalance API owner (Streck, separate team)** — publishes an
  OpenAPI contract we consume; expects us to regenerate clients when they
  bump the contract.

## User outcomes

1. A client posts `{ attacker, target, iterations }` and receives
   `{ distribution: {damage: probability}, percentiles: {p50,p90,p99}, mean, variance }`.
2. The response includes a `balance_adjustments` block reflecting the
   latest ExternalBalance data (e.g. +1 to wound for a flagged unit).
3. Existing `/calculate` callers see **no** behaviour change.

## Functional requirements

- FR-1: The system shall expose `POST /api/v1/calculate/simulate-distribution`
  accepting a `SimulationRequest` (attacker, target, iterations, seed?).
- FR-2: The system shall return a `DistributionResponse` containing
  `{ distribution, percentiles (p50/p90/p99), mean, variance,
  iterations_run, balance_adjustments }`.
- FR-3: The system shall reuse `EnhancedCombatCalculator` for the
  underlying Monte Carlo loop — a separate forked calculator is rejected.
- FR-4: The system shall call `ExternalBalanceClient.get_adjustments(unit_id)`
  before running the simulation and apply the returned modifiers.
- FR-5: The system shall fall back to "no adjustments applied" when
  ExternalBalance returns 5xx or times out (>2s), and shall surface
  `balance_adjustments.source = "fallback"` in the response.
- FR-6: The system shall preserve the existing `POST /calculate` contract
  byte-for-byte. `/calculate` tests must continue to pass unchanged.
- FR-7: `iterations` shall be capped at 50_000 (matching the existing
  `/calculate` cap).

## Non-functional requirements

- NFR-1: P95 added latency versus `/calculate` at 10k iterations: ≤ +150ms
  (the external call is the dominant new cost).
- NFR-2: ExternalBalance client uses `httpx.AsyncClient` with a 2s timeout
  and 1 retry on 5xx; no retry on 4xx.
- NFR-3: The ExternalBalance OpenAPI contract is checked into
  `contracts/external-balance.openapi.yaml` with a `.hash` file;
  `contract-drift-detection` skill guards regeneration.
- NFR-4: The Pydantic schema for `SimulationRequest` extends
  `CombatScenarioRequest` via composition (shared `attacker_unit`,
  `attacker_weapon`, `defender_unit`) — no copy-paste.

## Acceptance criteria

- AC-1: New endpoint returns a well-formed `DistributionResponse` for a
  known Space Marine vs Ork Boy scenario (deterministic with seed).
- AC-2: `POST /calculate` response bytes on the canonical scenario equal
  the pre-change baseline (captured in a characterization test).
- AC-3: Injecting a fake `ExternalBalanceClient` raising `httpx.TimeoutException`
  produces a response with `balance_adjustments.source = "fallback"`.
- AC-4: `contracts/external-balance.openapi.yaml` hash matches the hash
  checked into `external-balance.openapi.yaml.hash`; regen script ran
  cleanly.
- AC-5: All existing backend tests (`pytest tests/ -k "calculations or combat"`)
  pass unchanged — no skips, no xfails.

## Out of scope

- WebSocket streaming of partial distributions (future).
- Frontend UI changes (a later spec).
- Mutating ExternalBalance (read-only integration).
- Authentication beyond whatever `/calculate` already enforces.

## Open questions

- None (all resolved during `/clarify`).

## Brownfield notes (soup-specific; not part of EARS)

- **Extends:** `specs/<existing>/combat-calculator.md` (not present in the
  warhammer repo — a gap; see report).
- **Files touched (planned):**
  - `backend/app/api/calculations.py` (add route, no edit to existing)
  - `backend/app/schemas/combat.py` (add `SimulationRequest`,
    `DistributionResponse`; do not edit existing schemas)
  - `backend/app/services/combat_calculator.py` (add
    `simulate_distribution_async`; do not edit `calculate_scenario_async`)
  - `backend/app/clients/external_balance.py` (new module)
  - `contracts/external-balance.openapi.yaml` (new)
- **Regression-baseline step:** required. See plan S1 (`characterization-tests`).
