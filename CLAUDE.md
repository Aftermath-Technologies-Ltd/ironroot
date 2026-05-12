# CLAUDE.md

Instructions for Claude when working in the IRONROOT repository. Read this before making any changes.

## What this repo is

IRONROOT is a research platform for studying AI agent evolution under adversarial pressure. The thesis: integrity constraints should function as evolutionary pressure on agents, not compliance add-ons.

The repo is two things bolted together:

1. **The integrity core** (~1k LOC). Append-only hash-chained belief store, content-addressed artifact store, verification gates (replay, regression, falsification, invariants). This is the real, defensible part.
2. **Research subsystems** (~14k LOC). Agents, orchestration, AGI, evolution, healing, cognition, world models, research. Most of this is currently RNG-driven simulation or stubs. Treat as experimental until proven otherwise.

The README documents only the integrity core's actual guarantees. Anything in subsystem code that claims more (e.g., "AGI campaign passing") is overselling and must be either deleted, renamed, or moved under `ironroot.experimental.*`.

Positioning is **research-first**. Commercial framings overclaim. Honest research positioning is the defensible one.

## Current state

The project is in active hardening per `upgrade-plan.md`. Five phases:

- **Phase 0.** Stop the bleeding: fix breakage, declare deps, enforce lint/types, quarantine experimental code, honest naming.
- **Phase 1.** Integrity core to production grade: monotonic `seq` + advisory locks, write-once enforcement, replay digest, single BeliefService.
- **Phase 2.** Promote three subsystem groups (gates, self-healing/orchestration, belief services) to real implementations.
- **Phase 3.** Surface integrity to operators (real `/health`, auth, real run lifecycle).
- **Phase 4.** Promotion pipeline for quarantined subsystems.

Before making changes, check which phase the work belongs to. Don't add new subsystem features while Phase 1 work is open. Don't write to PRIMARY beliefs from anything that depends on `random.*`.

Phase status lives in the session SQL `todos` table with kebab-case ids matching upgrade-plan.md section numbers (e.g., `phase-0-1-fix-start-all-import`). Dependencies are encoded in `todo_deps`.

## The split: integrity core vs experimental

### Integrity core (production-targeted)

```
src/ironroot/domain/                          ids, errors, monotonic time, named invariants
src/ironroot/cognition/memory/                append-only belief store, BeliefRecord
src/ironroot/storage/artifacts.py             content-addressed filesystem store
src/ironroot/verification/                    integrity, replay, regression, falsification, gate_service
src/ironroot/beliefs/belief_service.py        canonical BeliefService (richer of the two)
packages/core-ts/                             @ironroot/core TypeScript port (must stay byte-equivalent)
tests/integrity/                              adversarial fixtures for the core
```

### Experimental (quarantined, gated on promotion)

```
src/ironroot/agents/
src/ironroot/agi/
src/ironroot/cognition/strategies/
src/ironroot/cognition/planning/
src/ironroot/evolution/
src/ironroot/healing/                         restoration verifiers must call real gate service
src/ironroot/orchestration/executor.py        RNG-fabricated faults; must be replaced with FaultFixture
src/ironroot/research/
src/ironroot/world_models/
src/ironroot/ui_backend/                      no current consumer
```

Anything under `ironroot.experimental.*` is allowed to be imperfect but must not be cited in product claims.

## Hard rules (apply everywhere)

1. **No `random.*` or `numpy.random.*` in any code path that writes `MetricClass.PRIMARY` beliefs, or that a gate decision depends on.** A CI grep guard fails the build if `random.` appears in any module outside `ironroot.experimental.*` or `tests/`.
2. **Every gate result is itself a belief.** Inputs are digested, decision and evidence belief ids are recorded. Gates are replayable.
3. **No new public surface without a falsification test for at least one failure mode.** Negative tests are required, not optional. CI asserts each gate's "should-fail" fixture actually fails.
4. **Append-only means append-only.** Chain parent lookup uses the monotonic `seq` column under `FOR UPDATE` plus a per-chain Postgres advisory lock. Never `ORDER BY created_at DESC`. Writes are serialized per chain.
5. **Write-once means write-once.** `ArtifactStore.delete()` is not part of the public API. Any GC of orphaned uploads goes through `_unsafe_delete`, used only by a separate retention job, and logs a tamper-class event on every call.
6. **One BeliefService.** Canonical implementation is `src/ironroot/beliefs/belief_service.py`. The older `cognition/memory/belief_service.py` is being removed. Don't reintroduce a parallel service. A CI import-graph test asserts only one `BeliefService` class is exported.
7. **Typed writes only.** Use `service.append_observation(...)`, `service.append_inference(...)`, `service.append_gate_result(...)`. No free-form `MetricClass` strings at call sites.
8. **Provenance is required for any non-PRIMARY belief.** DB-enforced. Points at source beliefs or fixture ids.
9. **`datetime.now(UTC)`, never `datetime.utcnow()`.** Ruff's `DTZ` rule enforces this. The project minimum is Python 3.12.
10. **Breaking changes are allowed.** Project is `0.1.0`, alpha. Use Alembic migrations and changelog entries. Don't preserve broken behavior for compatibility's sake.

## Anti-patterns (already happened; don't repeat)

- **Naming oversell.** Commits like "AGI 5/5 Campaign FULLY PASSING" against RNG-tuned passes. Don't write claims the evidence can't support.
- **Bypassing migrations.** `start_all.sh` previously used `Base.metadata.create_all`. Always `alembic upgrade head`. Schema changes require a migration file.
- **Stub-as-real.** `verification/falsification.py` returned `falsified=False` unconditionally. `_check_regression` passed when no incidents existed (no tests run). `_check_replay` re-ran chain verification instead of comparing a stored digest. If a check can pass without doing work, it's not a check.
- **RNG-fabricated evidence.** `orchestration/executor.py:255-499` wrote `PRIMARY` observations from `rng.random()`. Replace with deterministic `FaultFixture` mechanism: faults declared as fixtures, applied to a sandboxed copy of the chain, actual observed effects recorded.
- **Self-healing theater.** `healing/restoration.py` `_apply_strategy`, `_verify_invariants`, `_verify_replay` unconditionally returned `True`; `_check_recurrence` used unseeded `random.random()`. Verifiers must call the actual gate service. Restoration outcomes are `OBSERVATION` or `INFERENCE` beliefs with provenance back to the fault fixture id, never `PRIMARY`.
- **Parent-lookup fork.** `SELECT ... ORDER BY created_at DESC LIMIT 1` with no row lock allows concurrent appends to fork the chain. Use `seq` + `FOR UPDATE` + advisory lock.
- **Shadow API surfaces.** `/health` hardcoded to `"ok"`. `/ui/events/stream` was an echo. `RunStatus.gate_status` always `None`. Celery `execute_run` a no-op. Delete or implement; don't ship in between.
- **Annotation/value mismatch.** `RestorationReport._restoration_history` annotated `list` but assigned `dict`. Types and values must agree; `mypy --strict` catches this when enforced.

## Verifying your work

Before declaring a change done:

1. **Run integrity tests** in `tests/integrity/` against adversarial fixtures (tampered rows, replayed rows, out-of-order writes). Tampering any field of any belief row in a test DB must cause the relevant gate to fail with a typed violation.
2. **Property-based concurrency tests** (`hypothesis`) for any chain-touching change. N concurrent appenders must produce a totally-ordered chain with zero forks. `verify_chain` clean after.
3. **Gate negative tests.** Every gate has at least one fixture that should fail. CI asserts it does. Empty-incident-list is never a regression pass.
4. **Cross-language parity.** Any change to `domain/`, `cognition/memory/append_only_store.py`, `storage/artifacts.py`, or `verification/` requires Python and TypeScript implementations to produce byte-identical results under `packages/core-ts/test/fixtures/`.
5. **End-to-end fixture flow.** For self-healing changes: inject a known fault, executor detects, restoration applies strategy, gates verify, result belief stored, second replay produces identical digest.
6. **Lint and types green.** `ruff check` and `mypy --strict` are blocking. No new `# noqa` or per-file ignores without a tracked debt ticket.

## Code conventions

- Python 3.12 minimum.
- Named exports and explicit imports. No wildcard imports.
- Type hints required on public functions. `mypy --strict` is blocking.
- Ruff is blocking. Auto-fix where safe, delete dead code aggressively.
- Decompose files over ~300 lines when boundaries make sense.
- Tests validate real behavior, not wiring. No mocks for things that can be tested directly.
- Error messages include what failed and what to do about it.
- Alembic for schema changes. Never `create_all` outside test fixtures.
- Every belief-layer DB op runs inside an explicit transaction with the right isolation level.
- `IdPrefix` Literal must include every prefix actually used at call sites (`campaign`, `vio`, `rst`, etc.) or change `generate_id` to return `str`. Don't widen the Literal without adding the matching call-site test.

## Running things

```
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
./scripts/start_all.sh    # postgres + redis + alembic upgrade head
./scripts/run_once.sh     # uvicorn ironroot.main:app
pytest                    # full suite; mypy --strict and ruff are blocking
```

TypeScript port:

```
cd packages/core-ts && npm install && npm test
```

Refuse to start in non-debug if the DB password is empty or equals `changeme`. CORS in debug uses explicit `http://localhost:*` origins with `allow_credentials=True`. Production uses a settings-driven allowlist. `["*"]` plus `allow_credentials=True` is browser-rejected and forbidden.

## Reference

- `upgrade-plan.md`. Canonical plan. Phase numbering and section ids are authoritative.
- `README.md`. Documents only the integrity core's actual guarantees. Don't add subsystem claims here.
- `EXPERIMENTAL.md`. Every subsystem currently quarantined, with one-line honest descriptions.
- `docs/invariants/<subsystem>.md`. Invariants for subsystems promoted out of experimental.

## Promotion criteria (Phase 4)

A subsystem moves from `ironroot.experimental.*` to supported only after satisfying all of:

1. No `random.*` in any non-test path.
2. Writes only typed beliefs with real `provenance`.
3. At least one falsifiable claim registered with the falsification gate.
4. Regression suite that includes one fixture that should fail and one that should pass.
5. Documented invariants in `docs/invariants/<subsystem>.md`.
6. `EXPERIMENTAL.md` entry flipped from `experimental` to `supported`.

Likely first graduates: subsets of `research/`, simpler parts of `world_models/`. Likely long-term experimental: `agi/`, `evolution/`, large parts of `cognition/`.

## When uncertain

If the change crosses the integrity boundary, default to caution: surface the uncertainty before writing. The integrity core's guarantees are the only thing this project actually claims. Eroding them silently is worse than shipping nothing.
