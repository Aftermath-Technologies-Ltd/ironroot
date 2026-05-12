# world_models — documented invariants

Status: **supported** (graduated from experimental at Phase 4 closeout,
2026-05-12).

The `ironroot.world_models` subsystem provides a deterministic
`WorldModelRegistry` that stores `WorldModelSpec` and `EvaluationReport`
records as content-addressed artifacts on the existing artifact store. The
subsystem itself writes **no beliefs** to the chain — provenance flows
through the artifact store, which already enforces write-once / content
addressing at the integrity-core layer.

These invariants are the falsifiable claims the subsystem makes about its
own outputs. Each one has a registered falsifier or regression check, and
each one is exercised by at least one fixture under
`tests/promotion/test_world_models_promotion.py`.

## I1 — Evaluation artifact well-formedness

> For every run, every `world_model_evaluation` artifact attached to that
> run decodes as a JSON dictionary, hashes to its stored `content_hash`,
> declares every field present on `EvaluationReport.to_dict()`, and reports
> `counterfactual_accuracy`, `intervention_success_rate`, and
> `causal_consistency_score` in the closed interval `[0, 1]`.

**Falsifier.** `world_models.evaluation_artifact_well_formed`, registered
with `verification.falsification.get_claim_registry()` at package import.
Implemented in `src/ironroot/world_models/invariants.py`.

**Failure modes.** The falsifier flags:

- artifact bytes missing from disk or hashing to a different value
  (delegated to `ArtifactStore.verify`),
- payload that does not decode as UTF-8 JSON,
- payload that decodes to anything other than a dict,
- payload missing any required field, or
- any of the three accuracy fields outside `[0, 1]`.

**Vacuous case.** A run with zero evaluation artifacts satisfies the
invariant trivially — the falsifier returns `falsified=False` with
`rows_examined=0`. This is intentional: the gate must not invent failure
where the subsystem produced no output.

## I2 — Spec presence under evaluation

> If a run carries any `world_model_evaluation` artifact, it must also
> carry at least one `world_model_spec` artifact.

**Check.** `spec_present_when_evaluation_present`, in the
`world_models_promotion_suite` regression suite (run_kind
`world_models_promotion`).

**Why.** `WorldModelRegistry.evaluate_model` raises if the model_id under
evaluation hasn't been registered first, so an evaluation artifact
without a spec on the same run means the chain has lost provenance back
to the registering write — a regression.

**Vacuous case.** Same as I1: a run with no evaluation artifacts passes
without examining any rows.

## I3 — Evaluation references known spec

> Every `world_model_evaluation` artifact's `model_id` field matches the
> `model_id` of at least one `world_model_spec` artifact on the same run.

**Check.** `evaluation_references_known_spec`, in the same suite as I2.

**Why.** I2 establishes a spec exists; I3 establishes the *specific*
spec the evaluation references is the one stored. The pair together
rules out evaluation artifacts injected from outside the registry.

**Failure modes.** The check flags evaluation rows whose JSON payload
doesn't decode, isn't a dict, or names a `model_id` not present in any
spec artifact for the run.

## How these are exercised

`tests/promotion/test_world_models_promotion.py` builds two end-to-end
fixtures against an in-memory aiosqlite session:

- **should-pass.** Registers a `SimpleCausalModel`, runs `evaluate_model`
  with a counterfactual query, asserts I1/I2/I3 all hold (the
  falsifier returns `falsified=False`, the suite's `passed=True`).
- **should-fail.** Stores a *malformed* evaluation artifact directly
  via `ArtifactService.store_artifact` (the registry would never emit
  this shape), asserts the falsifier returns `falsified=True` and the
  suite's `passed=False` with the appropriate check name in
  `failed_checks()`.

## Operational notes

- The claim and suite register at package import via
  `register_with_default_registries()`. Registration is idempotent.
- No `random.*` is used anywhere in the subsystem; the deterministic
  fixture pattern is sufficient. The CI RNG guard
  (`scripts/check_no_random_in_core.py`) treats this subsystem as
  production code (it is no longer in `EXPERIMENTAL_MODULE_PREFIXES`).
- The subsystem writes no beliefs. Phase 2c.3 provenance is therefore
  vacuously satisfied. If a future commit adds belief writes from this
  subsystem, those writes MUST go through `BeliefService.append_*` and
  carry a `ProvenanceRef` pointing at the source spec / evaluation
  artifact, or the audit will fail criterion 2.
