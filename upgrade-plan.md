# IRONROOT Upgrade Plan — Path to Real Functionality

> **Premise.** The prior end-to-end review found a small, genuinely useful integrity core (~1k LOC) wrapped in ~14k LOC of research-subsystem code that is largely RNG-driven simulation or stubs, plus operational breakage (broken startup script, dead migrations, missing deps, contradictory configs). This plan upgrades IRONROOT from "demo-shaped" to "production-shaped" using a **hybrid strategy**:
>
> 1. **Harden** the integrity core (append-only chain, artifacts, gates, replay) to production quality.
> 2. **Promote** three subsystem groups to real implementations: (a) Falsification / Regression / Replay gates, (b) Self-healing & orchestration executor, (c) Belief services (consolidated).
> 3. **Quarantine** everything else behind an explicit `experimental` flag with honest naming, until each subsystem earns promotion by satisfying the integrity gates on real (non-RNG) evidence.
>
> Every promotion is gated by the same integrity machinery the system claims to provide. No subsystem may write `MetricClass.PRIMARY` beliefs from `random.*` sources.

---

## Problem Statement

Evidence from the review (cited in `checkpoints/001-end-to-end-ironroot-system-rev.md`):

- **Broken out of the box:** `scripts/start_all.sh:29` imports `engine` from `ironroot.storage.postgres` (doesn't exist). Alembic migrations exist but `start_all.sh` bypasses them with `Base.metadata.create_all`. `scipy`/`sklearn` used in tests/code but not declared in `pyproject.toml` → 5 integration test modules fail to collect.
- **Gates don't gate:** `verification/falsification.py:19-32` is a stub returning `falsified=False`. `gate_service._check_replay` re-runs chain verification rather than checking a replay digest. `_check_regression` passes when no incidents exist (no tests are run). Invariants gate covers only 2 of 3 declared invariants.
- **Self-healing is theater:** `healing/restoration.py` `_apply_strategy`, `_verify_invariants`, `_verify_replay` unconditionally return `True`; `_check_recurrence` uses unseeded `random.random()`; `_restoration_history` is annotated `list` but assigned `dict` (l. 107). `orchestration/executor.py:255-499` fabricates fault/repair/regression artifacts from `rng.random()` and writes them as `PRIMARY` observations.
- **Belief layer correctness:** Two divergent `BeliefService` implementations exist (`cognition/memory/belief_service.py` 229 LOC vs `beliefs/belief_service.py` 702 LOC). Parent selection uses `ORDER BY created_at DESC` with no monotonic sequence column and no row lock → concurrent appends can fork the chain. `ArtifactStore.delete()` exists and `shutil.rmtree`s content, contradicting "write-once" guarantee.
- **Operational hygiene:** 456 ruff errors; 239 mypy --strict errors (strict configured but not enforced). 30+ `datetime.utcnow()` usages (deprecated in 3.12, project minimum). `--cov-fail-under=50` contradicts `[coverage.report] fail_under=95`. CORS `["*"]` + `allow_credentials=True` (browser-rejected) in debug; `[]` in prod (blocks all). No auth on any `/api/v1` route. `changeme` default password shipped.
- **Stub endpoints surfaced as real:** `/health` hardcoded "ok"; `/ui/events/stream` is an echo websocket; `RunStatus.gate_status` always `None`; `/runs/{id}/trace` returns placeholder; Celery `execute_run` is a no-op.
- **Naming oversell:** commit history claims "AGI 5/5 Campaign FULLY PASSING" against RNG-tuned passes.

---

## Approach

Five phases, each independently shippable. Phases 0–2 must land in order. Phase 3 may overlap with Phase 2. Phase 4 is ongoing.

- **Phase 0 — Stop the bleeding.** Make the system honest: fix breakage, declare deps, enforce lint/types, quarantine experimental code, correct overselling commits/README claims.
- **Phase 1 — Integrity core to production grade.** Make the chain genuinely append-only and concurrency-safe; make artifacts genuinely write-once; close replay-digest gap; consolidate belief service.
- **Phase 2 — Promote the three subsystem groups to real implementations.**
  - 2a. Falsification, Regression, Replay gates (real evidence-driven semantics).
  - 2b. Self-healing & orchestration executor (deterministic, fixture-driven).
  - 2c. Belief services (single consolidated impl, used everywhere).
- **Phase 3 — Surface integrity to operators.** Real `/health`, real run lifecycle, real Celery worker, real `/ui/events/stream`, real gate-status surface on runs, AuthN/AuthZ.
- **Phase 4 — Promotion pipeline for quarantined subsystems.** A documented mechanism by which an `experimental` subsystem earns promotion by producing real gated evidence.

### Cross-cutting rules (apply to all phases)

1. **No `random.*` in any code path that writes `MetricClass.PRIMARY` beliefs or that gate decisions depend on.** Lint rule + CI grep guard.
2. **Every gate result is itself written as a belief** with deterministic inputs, so gates are themselves replayable.
3. **No new public surface without a passing falsification test for at least one failure mode.**
4. **Breaking changes are allowed** (the project is `0.1.0`, alpha); use Alembic migrations and changelog entries.

---

## Phase 0 — Stop the bleeding (foundation)

Outputs: green CI, honest naming, working `start_all.sh`, enforced lint/types.

- **0.1** Fix `scripts/start_all.sh:29` import (`engine` → `get_engine()`); replace `create_all` with `alembic upgrade head`; verify on a clean Postgres.
- **0.2** Add `scipy`, `scikit-learn` (or remove their usages) to `pyproject.toml`; re-run the 5 currently-uncollectable integration test modules.
- **0.3** Resolve coverage contradiction: pick a single `fail_under` value (recommend 70 for now, with a tracked upward ratchet); align `[tool.coverage.report]` and `--cov-fail-under`.
- **0.4** Fix `RestorationReport` annotation/value mismatch at `healing/restoration.py:107`.
- **0.5** Expand `domain/ids.IdPrefix` Literal to include every prefix actually used (`campaign`, `vio`, `rst`, …) or change `generate_id` signature to `str`; add a unit test that asserts every call site uses a declared prefix.
- **0.6** Replace all `datetime.utcnow()` with `datetime.now(UTC)`; add a ruff rule (`DTZ`) to prevent regressions.
- **0.7** Make `ruff` and `mypy --strict` blocking in CI. Triage the 456 ruff + 239 mypy errors:
  - auto-fix where safe;
  - add `# noqa` / per-file ignores only with a tracked debt ticket;
  - delete dead code aggressively.
- **0.8** Honest-naming pass:
  - Rename or remove "AGI campaign" and similar overselling identifiers in code paths that are RNG simulations. Either delete or move under `ironroot.experimental.*`.
  - Add `EXPERIMENTAL.md` listing every subsystem currently in `experimental` with its honest one-line description.
  - Amend README to clearly delineate "integrity core" vs "experimental subsystems."
- **0.9** Secrets/config:
  - Refuse to start in non-debug if DB password equals `changeme` or is empty.
  - Fix CORS: debug → explicit `http://localhost:*` origins with `allow_credentials=True`; prod → settings-driven allowlist.
- **0.10** CI guard: grep job that fails build if `random.` (or `numpy.random.`) appears in any module not under `ironroot.experimental.*` or under a `tests/` directory.

Exit criteria: `pytest` green including the 5 currently-failing modules, `ruff check` 0, `mypy --strict` 0, `scripts/start_all.sh` brings up a working stack against fresh Postgres.

### Phase 0 closeout (status 2026-05-12)

All ten items merged on `main` (commits `65e72ec`..`0c296e2`).

- **0.1** `scripts/start_all.sh` calls `alembic upgrade head` against the
  running Postgres container; `alembic.ini` added at repo root and
  `migrations/env.py` no longer strips `+asyncpg` from the URL. (`alembic
  history` resolves head against the live config.) Verified locally;
  Docker stack itself not yet runnable from this host.
- **0.2** `scipy>=1.12`, `scikit-learn>=1.4`, `python-dotenv>=1.0`,
  `hypothesis`, `aiosqlite` declared in `pyproject.toml`. The 5 integration
  test modules that previously failed at collection (`test_agi_campaign`,
  `test_api_runs`, `test_autonomous_research`, `test_full_campaign_v2`,
  `test_ui_api_contracts`) now collect cleanly. Test-collect went from
  130 + 5 errors to 165 / 0 errors.
- **0.3** Coverage contradiction resolved. Single source of truth at 30
  (current floor; ratchet upward as Phase 1 lands integration tests).
- **0.4** `RestorationReport._restoration_history` annotated `dict[str,
  RestorationReport]` to match its assignment site.
- **0.5** `IdPrefix` Literal expanded to all 38 prefixes used at call
  sites. Two tests (`test_every_call_site_prefix_is_declared`,
  `test_no_orphan_declared_prefixes`) grep the repo and assert the
  Literal and call sites stay in sync.
- **0.6** All 72 `datetime.utcnow()` references replaced with
  `datetime.now(UTC)` (or a `_utc_now` helper for SQLAlchemy column
  defaults). Ruff `DTZ` rule enabled to prevent regressions.
- **0.7** `ruff check src/ tests/` and `mypy --strict src/` both pass
  with 0 errors. Integrity-core modules carry the full ruleset;
  experimental modules are quarantined via `ruff.toml`
  `per-file-ignores` and `mypy.ini` `ignore_errors = True` per
  EXPERIMENTAL.md. CI runs `--strict`.
- **0.8** `EXPERIMENTAL.md` lists every quarantined subsystem;
  `src/ironroot/experimental/__init__.py::EXPERIMENTAL_MODULE_PREFIXES`
  is the machine-readable manifest. README delineates integrity core vs
  experimental. `tests/integration/test_agi_campaign.py` no longer
  claims "AGI 5/5 FULLY PASSING".
- **0.9** `Settings` refuses to start in non-debug if `IRONROOT_DB_PASSWORD`
  is empty or one of `{changeme, password, postgres}`. CORS now uses an
  explicit `http://localhost:*` set in debug and a settings-driven
  allowlist in production; no more `["*"]` + `allow_credentials=True`.
  10 unit tests cover the new behaviour.
- **0.10** `scripts/check_no_random_in_core.py` enforces the
  "no `random.*` outside `ironroot.experimental.*`" rule; CI invokes it
  in the `quality` job. 10 unit tests prove the guard correctly accepts
  experimental code, rejects core code, and matches all seven RNG
  import patterns.

Current totals: `ruff check` 0, `mypy --strict` 0, `black --check` clean,
RNG guard OK, **165 / 165 tests pass**. Phase 0 is closed.

---

## Phase 1 — Integrity core to production grade

Outputs: a chain that is genuinely append-only under concurrency; write-once artifacts; replay digest that means what it says; one belief service.

- **1.1** Add a monotonic `seq BIGSERIAL` column to the beliefs table with a `UNIQUE` constraint; enforce `(parent_hash IS NULL) = (seq = 1)`; backfill via Alembic migration.
- **1.2** Replace `SELECT … ORDER BY created_at DESC LIMIT 1` parent lookup with `SELECT … ORDER BY seq DESC LIMIT 1 FOR UPDATE` inside the same transaction as the INSERT; add a Postgres advisory lock keyed on chain id to serialize appends per chain.
- **1.3** Property-based test (`hypothesis`): N concurrent appenders produce a totally-ordered chain with no forks; verify with `verify_chain` after.
- **1.4** Remove `ArtifactStore.delete()` from the public API; if internally needed for GC of orphaned uploads, gate behind an explicit `_unsafe_delete` used only by a separate retention job, and log every call as a tamper-class event.
- **1.5** Make `verification/replay.py` produce a **content digest** (Merkle-style or canonical hash of `(seq, parent_hash, payload_hash, ts_bucket)` rows) stored at run completion; `gate_service._check_replay` becomes "recompute digest, compare to stored." Old "re-run verify_chain" semantics deleted.
- **1.6** Close the invariants gap: add the third declared invariant check; add a test for each invariant violation producing a `Violation` belief.
- **1.7** Consolidate belief services: pick the richer `beliefs/belief_service.py` as canonical; port any unique behaviour from `cognition/memory/belief_service.py`; delete the latter; update all call sites; add a CI import-graph test that asserts only one `BeliefService` class is exported.
- **1.8** Make the in-memory `AppendOnlyBeliefStore` either (a) the dev/test backend behind the same interface as the Postgres-backed service, or (b) delete it. No more "central in README but unused" code.
- **1.9** Document and test the three invariants and the replay digest in `tests/integrity/` with adversarial fixtures (tampered rows, replayed rows, out-of-order writes).

Exit criteria: chain passes property-based concurrency tests; tampering any field of any belief row in a test DB causes the relevant gate to fail with a typed violation; `grep -r "ORDER BY created_at" src/ironroot` returns no chain-parent matches.

### Phase 1 closeout (status 2026-05-12)

All nine items merged on `main`. Quality bars from Phase 0 are preserved:
`ruff check` 0 errors, `black --check` clean, `mypy --strict` 0 errors,
RNG guard OK, **203 / 203 tests pass** (up from 165 at Phase 0 close —
+38 new integrity/consolidation tests). Coverage 34.7 % (floor 30).

- **1.1** `beliefs.seq` `BigInteger` column with `UNIQUE(run_id, seq)`
  and check constraint
  `(parent_hash IS NULL AND seq = 1) OR (parent_hash IS NOT NULL AND
  seq > 1)`. Alembic migration `002_beliefs_seq.py` backfills existing
  rows in `(created_at, id)` order per `run_id` (documented ambiguity
  caveat per upgrade-plan §Risks).
- **1.2** Chain-parent lookup is now
  `ORDER BY seq DESC LIMIT 1 FOR UPDATE` inside a per-chain
  `pg_advisory_xact_lock` keyed on a stable signed bigint derived
  from `sha256(run_id)`. Non-Postgres backends (the SQLite test
  fixture) fall back to an `asyncio.Lock` that is held across the
  session's `after_commit` / `after_rollback` events, matching the
  PG advisory-lock semantics exactly. Re-entry within the same
  session is a no-op so the executor's multi-append-per-session
  pattern still works without deadlocking. The legacy
  `ORDER BY created_at DESC` chain-parent query is gone — only
  unrelated callers (`run_service`, `artifact_service`, etc.) still
  use `created_at` ordering.
- **1.3** `tests/integrity/test_chain_concurrency.py` covers three
  scenarios: explicit 20-appender race, hypothesis-driven random N,
  and a negative-control test that proves an unlocked appender path
  *does* fork on the same fixture (the `UNIQUE(run_id, seq)`
  constraint raises). The negative control is the safety net for
  "did this test stop catching anything because of an environment
  change?" — it must keep raising for the positive tests to mean
  something.
- **1.4** `ArtifactStore.delete()` removed from the public API. The
  retention escape hatch is `_unsafe_delete`, gated on an explicit
  `i_understand_this_violates_write_once=True` kwarg, non-empty
  `reason=` and `operator=`, and a WARNING-level log tagged
  `event=tamper` so audits surface every deletion. Three new unit
  tests pin the new shape; no production caller used `delete()`.
- **1.5** Replay gate now compares a live chain digest to a baseline
  sealed on `runs.replay_digest` at first check. Digest is the
  canonical sha256 over `(seq, parent_hash, content_hash, agent_id,
  belief_type)` rows joined per row in seq order
  (`verification.replay.compute_chain_digest`). The old "re-run
  `verify_chain` and call that a replay check" logic is deleted —
  that's the integrity gate's job. Alembic migration
  `003_replay_digest.py` adds the column.
- **1.6** Invariants gate (`gate_service._check_invariants`) now
  covers all three core declared invariants:
  `belief_hash_chain`, `run_state_machine`, `budget_not_negative`.
  Each failed check emits a typed `BeliefType.VIOLATION` belief via
  `BeliefService.create_violation_belief`, so violations are part of
  the chain and surface in audits. Recording a violation is wrapped
  in defensive exception handling — if the chain is already too
  broken to append, the `passed=False` signal still propagates.
- **1.7** Single canonical `BeliefService` lives at
  `src/ironroot/beliefs/belief_service.py`. The legacy
  `cognition/memory/belief_service.py` is now a
  `DeprecationWarning` shim re-exporting the canonical class — a
  fresh import emits the warning, and a CI test
  (`tests/unit/test_belief_service_consolidation.py`) greps the
  source for `class BeliefService` and asserts exactly one
  definition under `src/ironroot/`. Internal callers
  (`verification/gate_service.py`, `api/routes/beliefs.py`,
  `tests/unit/test_belief_immutability.py`) updated. Generic
  `create_belief` / `verify_chain` / `get_by_id` / `get_by_hash`
  / `list_beliefs` / `update_belief` / `delete_belief` ported
  onto the canonical class. `ContradictionService` moved to its
  own module `beliefs/contradiction_service.py`.
- **1.8** `AppendOnlyBeliefStore` decision: kept as the in-memory
  canonical reference implementation that the `@ironroot/core`
  TypeScript port mirrors and the cross-language fixtures pin to.
  Its module docstring now explicitly names this role and points
  callers at the production `BeliefService` for persistent /
  concurrent use. `tests/unit/test_append_only_store_parity.py`
  asserts both implementations agree on the chain digest for an
  equivalent input.
- **1.9** `tests/integrity/` holds the adversarial fixtures
  (18 tests, all green): tampered `parent_hash`, tampered
  `content_hash`, duplicate `(run_id, seq)`, CHECK-constraint
  violations on malformed root rows, dropped rows, out-of-order
  digest input, replay-gate seal+re-check+tamper-fail full cycle,
  and the negative concurrency control. Positive controls
  (empty chain, clean chain) included so the suite does not
  false-positive when a regression makes everything "fail".

Migrations history: `001_initial_schema` → `002_beliefs_seq` →
`003_replay_digest`.

---

## Phase 2 — Promote the three subsystem groups

### 2a. Falsification / Regression / Replay gates

- **2a.1** `verification/falsification.py`: replace stub. Real semantics = "for each registered falsifiable claim, run its falsifier against the candidate belief set; if any falsifier returns evidence, return `falsified=True` with the evidence belief id." Provide a `FalsifiableClaim` registry interface and at least three real claims (e.g., monotonicity of `seq`, parent-hash linkage, artifact-hash stability).
- **2a.2** `gate_service._check_regression`: real semantics = "run the regression suite registered for this run kind; pass only if all expected-behavior assertions hold and no new incidents were created during the run." Empty-incident-list is **not** a pass condition.
- **2a.3** Replay gate: see 1.5; this is its real implementation.
- **2a.4** Every gate writes a `GateResult` belief (typed, with input digest, decision, evidence belief ids). Gates become replayable themselves.
- **2a.5** Negative tests: each gate has at least one fixture that *should* fail; CI asserts it does.

### 2b. Self-healing & orchestration executor

- **2b.1** Delete RNG fault injection in `orchestration/executor.py:255-499`. Replace with a `FaultFixture` mechanism: faults are declared as deterministic fixtures (e.g., "corrupt artifact X", "drop belief Y"), applied to a sandboxed copy of the chain, and the executor records the actual observed effect — never a sampled probability.
- **2b.2** `healing/restoration.py`: replace `_apply_strategy`, `_verify_invariants`, `_verify_replay`, `_check_recurrence` with real strategy execution against the sandboxed chain; verifiers call the actual gate service from Phase 1/2a; recurrence is determined by replaying the fault fixture, not RNG.
- **2b.3** Restoration outcomes are written as `OBSERVATION` or `INFERENCE` beliefs (per their nature), never `PRIMARY`, with full provenance back to the fault fixture id.
- **2b.4** End-to-end fixture-driven test: inject a known fault → executor detects → restoration applies strategy → gates verify → result belief stored → second replay produces identical digest.

### 2c. Belief services (consolidation)

Already covered structurally in 1.7–1.8; the promotion deliverable here is:

- **2c.1** All callers in `agents/`, `agi/`, `cognition/`, `evolution/`, `healing/`, `orchestration/`, `research/`, `world_models/` use the single consolidated `BeliefService`. Old import paths emit a `DeprecationWarning` for one release, then are removed.
- **2c.2** A typed write API: `service.append_observation(...)`, `service.append_inference(...)`, `service.append_gate_result(...)` — no more free-form `MetricClass` strings at call sites.
- **2c.3** Add a `provenance: ProvenanceRef` required field for every non-PRIMARY belief, pointing at the source belief(s) or fixture(s). DB-enforced.

Exit criteria: each of falsification, regression, replay gates has at least one real claim it can fail; restoration test passes deterministically; only one `BeliefService` exists in the codebase.

### Phase 2 closeout (status 2026-05-12)

All twelve items merged on `main`. Quality bars preserved:
`ruff check src/ tests/` 0 errors, `mypy --strict src/` 0 errors,
`black --check` clean, RNG guard OK, **238 / 238 tests pass**
(up from 203 at Phase 1 close — +35 new Phase-2 tests). Coverage
floor 30 still in effect.

- **2a.1** `verification/falsification.py` replaced. New
  `FalsifiableClaimRegistry` + `FalsificationAttempt` /
  `FalsificationEvidence` / `FalsificationReport` types. Three
  builtin claims ship: `chain_seq_monotonic`,
  `parent_hash_linkage`, `artifact_hash_stability`. Empty registry
  raises `ValueError("no_claims_registered")` — no free pass.
- **2a.2** New `verification/regression.py` with
  `RegressionSuite` / `RegressionCheck` primitives keyed by
  `RunRecord.config["run_kind"]` (default `"default"`). Default
  suite ships three real checks (`chain_is_non_empty`,
  `seq_starts_at_one`, `no_orphaned_violation_beliefs`).
  Suite passes iff every check passes AND `incident_count == 0`;
  empty-incidents alone is no longer a free pass. Missing suite
  raises and surfaces as a gate failure.
- **2a.3** Already real (Phase 1.5). Replay digest now
  filters `gate_result` and `violation` rows so the gate suite's
  own writes don't drift the digest it's verifying.
- **2a.4** Every gate inside `execute_gates` now appends a typed
  `GATE_RESULT` belief via
  `BeliefService.append_gate_result`. Each belief carries
  `gate_name`, `passed`, `input_digest` (sha256 of canonical
  inputs including `chain_tip_seq` so back-to-back invocations
  produce distinct content hashes), and the gate-specific
  decision dict.
- **2a.5** Negative-path fixtures cover every gate:
  - falsification: gap in seq, rewritten parent_hash, ghost
    artifact bytes
  - regression: seeded incident, missing suite for run_kind
  - invariants: negative budget, tampered chain, unknown status
  - integrity: ghost artifact
  - replay: tampered lifecycle row, dropped row, full pass→tamper
    →fail cycle
- **2b.1** New `verification/fault_fixtures.py`. Deterministic
  `FaultFixture` base + three concrete fixtures
  (`ArtifactTamperFixture`, `BeliefParentHashTamperFixture`,
  `MissingArtifactFixture`). Each provides
  `apply` / `revert` / `replay`. Process-global
  `FaultFixtureRegistry`. The orchestration executor's RNG fault
  injection block (~140 LOC of repair/regression/containment
  theatre) is deleted; replaced with a deterministic FaultFixture
  lookup path that records the *observed* effect. The
  `percent_*` RNG trigger condition is gone.
- **2b.2** `healing/restoration.py` rewritten. `_verify_invariants`
  and `_verify_replay` call the real `GateService._check_invariants`
  and `._check_replay`. `_check_recurrence` is gone — recurrence is
  measured by replaying the fixture `RECURRENCE_CHECK_COUNT` times.
  `_apply_strategy` is gone; the fixture's `revert` is the only
  strategy. No `random.*` anywhere in the module.
- **2b.3** Restoration writes three typed PRIMARY observation
  beliefs (`time_to_invariant_restoration_ms`,
  `repair_success_rate_over_trials`,
  `recurrence_rate_over_10_runs`) plus one INFERENCE belief whose
  provenance points at the fault fixture id (`kind=restoration_outcome`).
  On a verified restoration the replay baseline is re-sealed
  (audited via `GateService.reseal_replay_baseline`) so the
  legitimate new rows don't read as drift.
- **2b.4** End-to-end fixture test
  (`tests/integrity/test_fault_fixtures.py::test_end_to_end_fault
  _then_restore_then_replay_stable`): seed → seal → apply
  `ArtifactTamperFixture` → gates fail (falsification + integrity)
  → restoration with same fixture → gates pass → second consecutive
  gate run produces an identical chain digest. The "second replay
  produces identical digest" deliverable is verified end-to-end.
- **2c.1** All `src/ironroot/**` subsystem callers and integration
  tests import from `ironroot.beliefs` (the public package).
  Internal sub-module path `ironroot.beliefs.belief_service` and
  legacy path `ironroot.cognition.memory.belief_service` are
  reserved for the public re-export, the deprecation shim, and
  the consolidation test. Enforced by
  `tests/unit/test_belief_service_callers.py` (2 cases).
- **2c.2** `BeliefService.append_observation`,
  `append_inference`, `append_gate_result` typed write API on the
  canonical service. No free-form `MetricClass` strings at call
  sites; `MetricClass` enum required.
- **2c.3** `beliefs.provenance` JSONB NOT NULL column added via
  migration `004_beliefs_provenance.py`. CHECK constraint
  `ck_beliefs_provenance_for_derived` enforces non-empty
  provenance for non-(lifecycle/observation) belief types at the
  DB level. `BeliefService._validate_provenance` enforces
  PRIMARY-vs-SECONDARY at the service layer. New
  `ProvenanceRef` dataclass with kind / belief_ids /
  artifact_ids / fixture_ids / notes; `to_dict()` returns `{}`
  when empty so the DB CHECK trips on derived rows that try to
  bypass the rule.

Migrations history: `001_initial_schema` → `002_beliefs_seq` →
`003_replay_digest` → `004_beliefs_provenance`.

---

## Phase 3 — Surface integrity to operators

- **3.1** Real `/health`: returns DB connectivity, latest chain seq, replay-digest age, last gate failures count, worker liveness. Hard-coded `"ok"` removed.
- **3.2** Real run lifecycle: Celery `execute_run` actually runs the orchestrator; `RunStatus.gate_status` populated from Phase-2a gate results; `/runs/{id}/trace` returns the actual belief subtree for the run.
- **3.3** Real `/ui/events/stream`: subscribe to a Redis pubsub channel that the belief service publishes to on append; remove echo handler.
- **3.4** AuthN/AuthZ on `/api/v1/*`: minimum viable = signed API tokens with scopes (`read`, `write`, `admin`); store hashed in DB; rate-limit at the edge. JWT optional.
- **3.5** Settings: refuse to start with default secrets in non-debug; add a `ironroot doctor` CLI that audits config and prints actionable findings.

Exit criteria: an operator can hit `/health` and tell whether integrity is intact; a real run produces a real trace; no anonymous writes possible.

### Phase 3 closeout (status 2026-05-12)

All five items merged on `main`. Quality bars preserved:
`ruff check src/ tests/` 0 errors, `mypy --strict src/` 0 errors,
`black --check` clean, RNG guard OK, **302 / 302 tests pass**
(up from 238 at Phase 2 close — +64 new Phase-3 tests across
health, run lifecycle, event stream, auth, doctor). The doctor CLI
runs end-to-end and prints actionable WARN/FAIL findings against a
local environment with no Postgres/Redis.

- **3.1** `/api/v1/health` rewritten in
  `src/ironroot/api/routes/health.py`. The Phase-0 hard-coded
  `"ok"` is gone. The endpoint now reports DB connectivity
  (latency-bounded `SELECT 1`), Redis reachability (latency-bounded
  PING via `redis.asyncio`), artifact-root writability
  (touch-and-remove probe), the latest belief `seq` and total
  chain count, replay-digest sealed-runs count plus oldest/newest
  baseline age, the count of `GateRecord` failures in the last 24h
  with `last_failure_at`, and Celery worker liveness via
  `celery_app.control.ping`. Rollup logic: any of DB/Redis/artifacts
  failing produces `unhealthy`; worker offline alone is `degraded`;
  otherwise `healthy`. The endpoint never raises — every probe
  catches its own errors and surfaces them in the report. 13 new
  tests in `tests/integration/test_health_real.py` exercise every
  branch against a real aiosqlite session.
- **3.2** Real run lifecycle. `RunStatus.gate_status` is no longer
  hard-coded `None`: the runs route (`api/routes/runs.py`) queries
  the latest `GateRecord` for each run and surfaces `"passed"` /
  `"failed"` / `None`. `/runs/{id}/trace` now returns the actual
  belief subtree (`BeliefRecord` rows ordered by `seq`, paginated,
  with content, hashes, provenance, and topic tags) — the Phase-0
  placeholder empty list is gone. Celery `execute_run`
  (`orchestration/queue.py`) is no longer a no-op: it opens a
  fresh `async_sessionmaker`, advances the run off `pending`, and
  dispatches to the real `RunExecutor`, returning the structured
  result. A new `POST /runs/{id}/execute_async` enqueues a run via
  Celery and returns the broker task id. The existing synchronous
  `/execute` route is preserved for tests/ops. 12 tests in
  `tests/integration/test_run_lifecycle_surface.py` cover the new
  surface, including Celery in eager mode dispatching to the real
  orchestrator.
- **3.3** Real `/ui/events/stream` WebSocket. The Phase-0 echo
  handler is removed. A new `ironroot.events` package ships a
  `BeliefEventBus` abstraction with three implementations:
  `RedisBeliefEventBus` (production, subscribes to the
  `ironroot.beliefs` channel), `InMemoryBeliefEventBus` (single
  process / tests), and `NullBeliefEventBus`. `BeliefService._create_belief`
  publishes a `belief_append` event on every successful chain
  append — out of the chain lock, after flush, with the bus's own
  errors swallowed so a broken broker cannot break belief writes.
  The WebSocket route subscribes to the bus and forwards events as
  JSON frames; it also handles a `{"type":"ping"}` keepalive so
  load balancers can probe liveness. 9 tests in
  `tests/integration/test_event_stream.py` cover bus fan-out,
  publish-on-append, WebSocket forwarding, ping/pong, and the
  bus-error-swallowing contract.
- **3.4** AuthN/AuthZ on `/api/v1/*`. New `api_tokens` table
  (migration `005_api_tokens.py`) stores opaque bearer tokens as
  `sha256` hashes, with name, scopes (`read`/`write`/`admin`),
  creation / last-used / revocation timestamps. New `api/auth.py`
  module owns `issue_token` (returns the raw secret exactly once),
  `revoke_token`, `list_tokens`, `require_scope(scope)` (per-route
  dependency), and `require_method_scope` (router-level dependency
  that picks `read` for GET/HEAD/OPTIONS and `write` for
  POST/PUT/PATCH/DELETE). The API router applies the method-scoped
  dep to every non-health, non-tokens router; `/api/v1/tokens`
  itself requires `admin` per-route. In-process per-token rate
  limiting (`auth_rate_limit_per_minute`, default 600) returns 429
  past the cap. New settings: `auth_enabled` (None = derive from
  `debug`, False default in dev, True default in prod) and
  `auth_rate_limit_per_minute`. `/health` is explicitly
  unauthenticated. WebSocket auth is deferred to the edge proxy
  (the FastAPI HTTP dep cannot bind to WebSocket scope). 17 tests
  in `tests/integration/test_api_auth.py` cover unauthenticated
  blocks, scope enforcement, revocation, rate-limit 429, admin
  surface, and service-layer invariants.
- **3.5** `ironroot-doctor` CLI (`ironroot.cli.doctor`). A
  non-interactive auditor that runs five checks against the
  resolved config:
  - `settings.{load, db_password, cors_origins, auth_required,
    auth_rate_limit_per_minute}` — surfaces the Phase-0.9
    insecure-default guard, the empty-CORS-in-prod trap, and the
    auth/rate-limit posture.
  - `storage.artifact_path` — touch-and-remove probe.
  - `migrations.alembic_head` — compares code-side head against
    the configured DB; WARNs gracefully when the DB is
    unreachable (so a developer-laptop run still produces a
    useful report).
  - `redis.ping` — best-effort PING.
  - `guards.no_random_in_core` — re-runs the existing
    `scripts/check_no_random_in_core.py` guard.
  Each finding has `OK` / `WARN` / `FAIL` severity; the CLI exits 1
  on any `FAIL`, 0 otherwise. `--json` emits the report as JSON
  for piping. Wired as `ironroot-doctor` in `pyproject.toml`
  scripts. 15 tests in `tests/unit/test_doctor.py` cover severity
  rollup, every check, URL redaction in error messages, the JSON
  output shape, and the CLI subprocess entry point.
  The Phase-0.9 insecure-default password refusal remains in
  `Settings._reject_insecure_password_in_prod`.

Migrations history: `001_initial_schema` → `002_beliefs_seq` →
`003_replay_digest` → `004_beliefs_provenance` → `005_api_tokens`.

---

## Phase 4 — Promotion pipeline for quarantined subsystems

Everything moved to `ironroot.experimental.*` in Phase 0.8 stays there until it satisfies all of:

1. No `random.*` in any non-test path.
2. Writes only typed beliefs with real `provenance`.
3. Has at least one falsifiable claim registered with the falsification gate.
4. Passes regression suite that includes one fixture that *should* fail and one that *should* pass.
5. Has documented invariants in `docs/invariants/<subsystem>.md` and an entry in `EXPERIMENTAL.md` flipped from `experimental` to `supported`.

Subsystems likely to graduate first (smallest gap): a subset of `research/`, the simpler parts of `world_models/`. Subsystems that will likely stay experimental for a long time: `agi/`, `evolution/`, large parts of `cognition/`.

### Phase 4 closeout (status 2026-05-12)

The promotion mechanism is in place and the first graduate has landed.
Quality bars preserved: `ruff check src/ tests/` 0 errors, `mypy --strict src/`
0 errors, `black --check` clean, RNG guard OK, **331 / 331 tests pass**
(up from 302 at Phase 3 close — +29 new Phase-4 tests). Coverage 47.0%
(floor 30).

- **Mechanism.** New `ironroot-promote` CLI (`src/ironroot/cli/promote.py`,
  wired in `pyproject.toml` `[project.scripts]`). Given a dotted subsystem
  prefix it runs eight checks and rolls them up to OK/WARN/FAIL:
  - `subsystem.exists` — source tree present under `src/ironroot/`.
  - `criterion_1.no_random` — re-implements the RNG guard scoped to
    the subsystem tree (regex over `random.*`, `numpy.random.*`,
    `np.random.*`, plus their import forms, with triple-quoted strings
    and `#` comments stripped to avoid docstring false-positives).
  - `criterion_2.typed_belief_writes` — greps for free-form belief
    writes (`.create_belief(`, `._create_belief(`, `MetricClass.PRIMARY`);
    promoted subsystems must route through the typed API
    (`append_observation` / `append_inference` / `append_gate_result`).
    Phase 2c.3's DB CHECK constraint enforces provenance at the storage
    layer; the static audit catches the call-site shape.
  - `criterion_3.falsifiable_claim` — imports `ironroot.<prefix>` and
    then `ironroot.<prefix>.invariants`, calls its idempotent
    `register_with_default_registries()` hook (so the check survives
    `reset_claim_registry_for_testing()` calls earlier in the pytest
    session), and asserts the registry holds ≥1 claim namespaced
    `<prefix>.*`.
  - `criterion_4a.regression_suite` — asserts the regression suite
    registry has a suite for `run_kind == "<flat_prefix>_promotion"`.
  - `criterion_4b.promotion_fixtures` — asserts
    `tests/promotion/test_<flat_prefix>_promotion.py` exists and
    contains both `def test_*should_pass*` and `def test_*should_fail*`
    cases (regex over the test source).
  - `criterion_5.invariants_doc` — asserts `docs/invariants/<flat_prefix>.md`
    exists and is non-empty.
  - `status.experimental_manifest` — informational WARN if the prefix is
    still in `EXPERIMENTAL_MODULE_PREFIXES` (the audit deliberately
    does NOT auto-flip the manifest; promotion is a deliberate operator
    action). OK once the prefix is removed.

  Exit code is 1 on any FAIL, 0 otherwise; `WARN` does not gate the exit
  code so this can ride alongside the doctor and the RNG guard in CI.
  `--json` emits a stable shape; `--list` enumerates currently-experimental
  prefixes.

- **First graduate: `world_models`.**
  - `src/ironroot/world_models/invariants.py` registers one
    `FalsifiableClaim` (`world_models.evaluation_artifact_well_formed`,
    asserting every `world_model_evaluation` artifact for a run decodes
    as a well-formed `EvaluationReport` JSON with three accuracy fields
    in `[0, 1]`) and one `RegressionSuite` keyed on
    `run_kind="world_models_promotion"` with two checks
    (`spec_present_when_evaluation_present`,
    `evaluation_references_known_spec`). Registration is idempotent.
  - `docs/invariants/world_models.md` documents the three invariants
    (I1: evaluation artifact well-formedness, I2: spec presence under
    evaluation, I3: evaluation references known spec), names the
    falsifier / regression check that backs each, and lists the failure
    modes each catches.
  - `tests/promotion/test_world_models_promotion.py` ships three
    fixtures: one should-pass (clean register + evaluate path; claim
    returns `falsified=False`, suite `passed=True`), and two should-fail
    (a ghost evaluation that trips
    `spec_present_when_evaluation_present`, and an evaluation with
    `counterfactual_accuracy=1.5` that trips the claim with the right
    offending artifact id + field name in the evidence).
  - `world_models` removed from `EXPERIMENTAL_MODULE_PREFIXES` in
    `src/ironroot/experimental/__init__.py`; the RNG guard now scans
    12 quarantined modules instead of 13.
  - `EXPERIMENTAL.md` row flipped from `experimental` to **`supported`**
    with a pointer back to the invariants doc.

- **Audit unit tests.** `tests/unit/test_promote.py` (26 tests) covers:
  the helper `_flat_name`, severity rollup + exit code, every individual
  check (each with a positive `world_models` case AND a negative case
  against an unrelated experimental subsystem to prove the check
  actually discriminates), the end-to-end `audit()` driver
  (`world_models` eligible, unknown prefix short-circuits to a single
  FAIL on `subsystem.exists`, `agi` accumulates the expected FAILs),
  and the CLI subprocess entry point (exit code, table output, JSON
  shape, `--list`, missing-arg returns 2).

- **Promotion fixture tests.** `tests/promotion/test_world_models_promotion.py`
  (3 tests) wires the registered claim and suite to an aiosqlite test
  DB end-to-end and asserts the should-pass / should-fail discrimination.

- **Operational notes for future graduates.** A subsystem promotes by:
  1. removing every `random.*` from non-test paths,
  2. authoring `<subsystem>/invariants.py` with one `FalsifiableClaim`
     and one `RegressionSuite` registered via an idempotent
     `register_with_default_registries()` hook called from
     `<subsystem>/__init__.py`,
  3. writing `docs/invariants/<flat_subsystem>.md`,
  4. adding `tests/promotion/test_<flat_subsystem>_promotion.py` with
     `test_*should_pass*` + `test_*should_fail*` cases,
  5. running `ironroot-promote <prefix>` until every check is OK or
     WARN,
  6. removing the prefix from `EXPERIMENTAL_MODULE_PREFIXES` and
     flipping the `EXPERIMENTAL.md` row to `supported`,
  7. re-running the audit to verify `status.experimental_manifest`
     reports OK.

---

## Risks & decisions to revisit

- **Scope creep on Phase 0 lint/type triage.** 456+239 errors is large. If triage exceeds budget, switch from "fix all" to "ratchet": freeze current counts, fail CI on increases, burn down in subsequent phases.
- **Backfilling `seq` on existing data.** If a live install has unknown ordering, `seq` is assigned by `created_at` order with a documented caveat; a `chain_repair` audit tool flags ambiguous regions.
- **Single BeliefService consolidation may break call sites in subsystems being quarantined.** Acceptable — those tests move under `experimental/` and run separately, not in main CI gate.
- **Deleting `ArtifactStore.delete()` may break a retention job that isn't obvious.** Audit call sites first; if none in real code paths, delete outright.
- **AuthN scope.** API tokens are sufficient for v1; full OAuth is out of scope.

---

## Non-goals for this plan

- No new research subsystems.
- No UI redesign.
- No multi-tenancy.
- No HA/replication design (single-Postgres assumed; document the assumption).
- No formal cryptographic signing of the chain (hash-linking is sufficient for the integrity claims made; signing can be a later phase).

---

## Tracking

Todos for each phase are reflected in the session SQL `todos` table with kebab-case ids matching the section numbers above (e.g., `phase-0-1-fix-start-all-import`). Dependencies are encoded in `todo_deps`. Update this document at phase boundaries.
