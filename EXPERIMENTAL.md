# EXPERIMENTAL

This file enumerates every subsystem in IRONROOT that is currently quarantined
as **experimental**. Experimental subsystems are allowed to be imperfect
(RNG-driven, stubbed, partially typed) but **must not be cited in product
claims**, and writes from these subsystems are forbidden from touching
`MetricClass.PRIMARY` beliefs or gate decisions.

The authoritative machine-readable list lives in
`src/ironroot/experimental/__init__.py::EXPERIMENTAL_MODULE_PREFIXES`. This
document mirrors that list with honest one-line descriptions and a current
status (`experimental` / `supported`).

A subsystem moves from `experimental` to `supported` only after satisfying
every clause of the Phase 4 promotion criteria in `upgrade-plan.md`.

| Dotted prefix              | Status        | Description                                                                                          |
|----------------------------|---------------|------------------------------------------------------------------------------------------------------|
| `agents`                   | experimental  | Builder/proposer/tester/verifier agent shells. Stubbed; no real LLM integration in the default path. |
| `agi`                      | experimental  | "AGI suite" — RNG-driven scenarios for adversarial, transfer, sustained, skills, tools, ensembles.    |
| `battery`                  | experimental  | RNG-driven scoring batteries used by the AGI evaluation harness.                                      |
| `capabilities`             | experimental  | Capability descriptors used by the agent shells; no enforcement yet.                                  |
| `cognition.planning`       | experimental  | Plan-tree primitives; not integrated with the integrity core.                                         |
| `cognition.strategies`     | experimental  | Strategy registry / mutation / evolution. Uses `random.*` for selection; cannot write PRIMARY beliefs.|
| `evolution`                | experimental  | Population-level evolution loop wrappers around `cognition.strategies`.                               |
| `healing`                  | experimental  | Self-healing restoration. Strategy verifiers currently return True unconditionally; see Phase 2b.     |
| `orchestration.executor`   | experimental  | Run-execution loop with RNG-fabricated fault/repair/regression evidence; see Phase 2b for fixtures.   |
| `reality`                  | experimental  | "Reality source" registry (RNG simulators, sklearn dataset wrappers). No real external IO.            |
| `research`                 | experimental  | Research-question + hypothesis generation. Mixed real/RNG; needs Phase 4 audit before promotion.      |
| `ui_backend`               | experimental  | WebSocket event bridge. No current consumer; previous React UI removed.                               |
| `world_models`             | **supported** | Deterministic registry of WorldModelSpec + EvaluationReport artifacts. Phase 4 graduate 2026-05-12. See `docs/invariants/world_models.md`. |

## Integrity core (NOT experimental, subject to production-grade rules)

These modules are explicitly **not** in the experimental quarantine and are
held to the hard rules in `CLAUDE.md`:

- `src/ironroot/domain/`
- `src/ironroot/cognition/memory/`
- `src/ironroot/storage/artifacts.py`
- `src/ironroot/storage/artifact_service.py`
- `src/ironroot/storage/postgres.py`
- `src/ironroot/storage/models.py`
- `src/ironroot/verification/`
- `src/ironroot/beliefs/belief_service.py`
- `src/ironroot/api/` (must remain experimental-free at the integrity surface; see Phase 3 for AuthN)
- `src/ironroot/settings.py`
- `src/ironroot/main.py`
- `packages/core-ts/` (TypeScript port of the integrity primitives — must stay byte-equivalent)

## Promotion criteria (Phase 4 summary)

A subsystem moves from `experimental` to `supported` only after:

1. No `random.*` (or `numpy.random.*`) in any non-test code path.
2. Writes only typed beliefs with real `provenance`.
3. At least one falsifiable claim registered with the falsification gate.
4. Regression suite includes one fixture that *should* fail and one that *should* pass.
5. Documented invariants in `docs/invariants/<subsystem>.md`.
6. This file's entry flipped from `experimental` to `supported`.
