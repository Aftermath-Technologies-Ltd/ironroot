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

---

## Phase 3 — Surface integrity to operators

- **3.1** Real `/health`: returns DB connectivity, latest chain seq, replay-digest age, last gate failures count, worker liveness. Hard-coded `"ok"` removed.
- **3.2** Real run lifecycle: Celery `execute_run` actually runs the orchestrator; `RunStatus.gate_status` populated from Phase-2a gate results; `/runs/{id}/trace` returns the actual belief subtree for the run.
- **3.3** Real `/ui/events/stream`: subscribe to a Redis pubsub channel that the belief service publishes to on append; remove echo handler.
- **3.4** AuthN/AuthZ on `/api/v1/*`: minimum viable = signed API tokens with scopes (`read`, `write`, `admin`); store hashed in DB; rate-limit at the edge. JWT optional.
- **3.5** Settings: refuse to start with default secrets in non-debug; add a `ironroot doctor` CLI that audits config and prints actionable findings.

Exit criteria: an operator can hit `/health` and tell whether integrity is intact; a real run produces a real trace; no anonymous writes possible.

---

## Phase 4 — Promotion pipeline for quarantined subsystems

Everything moved to `ironroot.experimental.*` in Phase 0.8 stays there until it satisfies all of:

1. No `random.*` in any non-test path.
2. Writes only typed beliefs with real `provenance`.
3. Has at least one falsifiable claim registered with the falsification gate.
4. Passes regression suite that includes one fixture that *should* fail and one that *should* pass.
5. Has documented invariants in `docs/invariants/<subsystem>.md` and an entry in `EXPERIMENTAL.md` flipped from `experimental` to `supported`.

Subsystems likely to graduate first (smallest gap): a subset of `research/`, the simpler parts of `world_models/`. Subsystems that will likely stay experimental for a long time: `agi/`, `evolution/`, large parts of `cognition/`.

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
