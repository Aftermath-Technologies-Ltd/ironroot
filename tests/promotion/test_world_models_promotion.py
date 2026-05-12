# Author: Bradley R. Kinnard
"""Phase 4 promotion fixtures for ``ironroot.world_models``.

The promotion audit (``ironroot-promote world_models``) expects this file
to declare at least one ``test_*should_pass*`` and one ``test_*should_fail*``
case. Each case drives a deliberately-shaped run through the registered
FalsifiableClaim and RegressionSuite and asserts the gate's verdict.

Together these fixtures prove the registered claim and suite actually
distinguish well-formed evaluation artifacts from malformed ones — the
should-fail case must fail for a real, named reason, not by accident.
"""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import async_sessionmaker

from ironroot.storage.artifact_service import get_artifact_service
from ironroot.verification.falsification import (
    get_claim_registry,
    run_falsification,
)
from ironroot.verification.regression import (
    get_regression_registry,
    run_regression,
)
from ironroot.world_models import (
    CounterfactualQuery,
    SimpleCausalModel,
    get_world_model_registry,
)
from ironroot.world_models.invariants import (
    ARTIFACT_TYPE_EVALUATION,
    CLAIM_NAME,
    SUITE_RUN_KIND,
)


async def _seed_clean_world_model_run(session_factory: async_sessionmaker, run_id: str) -> None:
    """Drive the registry's happy-path: register one model + evaluate it.

    Produces one ``world_model_spec`` artifact and one
    ``world_model_evaluation`` artifact on ``run_id`` — exactly the shape
    the claim and suite are designed to wave through.
    """
    registry = get_world_model_registry()
    model = SimpleCausalModel(
        domain="test_promotion",
        coefficients={"a_to_b": 2.0, "b_to_c": 3.0},
    )
    async with session_factory() as session:
        await registry.register_model(
            session=session,
            model=model,
            training_data=b"deterministic-training-fixture",
            run_id=run_id,
        )
        await session.commit()

    async with session_factory() as session:
        await registry.evaluate_model(
            session=session,
            model_id=model.model_id,
            queries=[
                CounterfactualQuery(
                    query_id="cf-1",
                    condition="a=2",
                    intervention={"a": 2.0},
                    outcome_variable="c",
                    expected_outcome=12.0,
                ),
            ],
            run_id=run_id,
        )
        await session.commit()


# ---------------------------------------------------------------------------
# should-pass: clean run satisfies the claim AND the regression suite.
# ---------------------------------------------------------------------------


async def test_world_models_should_pass_clean_run(
    session_factory: async_sessionmaker, run_id: str
) -> None:
    """Happy path: register + evaluate one model; claim and suite both pass."""
    await _seed_clean_world_model_run(session_factory, run_id)

    # FalsifiableClaim — must run and return falsified=False with no evidence.
    async with session_factory() as session:
        report = await run_falsification(session, run_id, registry=get_claim_registry())
    by_name = {a.claim_name: a for a in report.attempts}
    assert CLAIM_NAME in by_name, (
        f"world_models claim missing from registry; " f"got: {sorted(by_name.keys())}"
    )
    attempt = by_name[CLAIM_NAME]
    assert attempt.falsified is False
    assert attempt.evidence is None
    assert attempt.rows_examined == 1

    # RegressionSuite — keyed off run.config["run_kind"] (set by the fixture
    # to "world_models_promotion"), all checks pass, zero incidents.
    async with session_factory() as session:
        suite_report = await run_regression(session, run_id)
    assert suite_report.run_kind == SUITE_RUN_KIND
    assert suite_report.passed is True
    assert suite_report.failed_checks() == ()


# ---------------------------------------------------------------------------
# should-fail: malformed evaluation artifact triggers the claim AND the suite.
# ---------------------------------------------------------------------------


async def test_world_models_should_fail_malformed_evaluation(
    session_factory: async_sessionmaker, run_id: str
) -> None:
    """Injecting an evaluation artifact with no matching spec must fail.

    The artifact decodes as JSON and the field shape is valid, so I1 passes
    — but its ``model_id`` was never registered against this run, so I3
    (``evaluation_references_known_spec``) trips. This is the should-fail
    fixture demanded by Phase 4 criterion #4.
    """
    artifact_service = get_artifact_service()
    ghost_evaluation = {
        "model_id": "ghost_model_not_registered",
        "counterfactual_accuracy": 1.0,
        "intervention_success_rate": 1.0,
        "causal_consistency_score": 1.0,
        "num_queries_tested": 0,
        "failed_queries": [],
        "evaluated_at": "2026-05-12T00:00:00+00:00",
    }
    async with session_factory() as session:
        await artifact_service.store_artifact(
            session=session,
            data=json.dumps(ghost_evaluation).encode(),
            artifact_type=ARTIFACT_TYPE_EVALUATION,
            created_by="test_promotion_should_fail",
            run_id=run_id,
            filename="ghost_eval.json",
        )
        await session.commit()

    # Claim — well-formed JSON in [0,1] range, so the claim alone holds.
    async with session_factory() as session:
        report = await run_falsification(session, run_id, registry=get_claim_registry())
    by_name = {a.claim_name: a for a in report.attempts}
    assert by_name[CLAIM_NAME].falsified is False, (
        "Field-level claim should hold for the ghost artifact; " "provenance is the suite's job"
    )

    # Suite — must trip the spec-presence check (I2). The evaluation is
    # well-formed but provenance back to a registered spec is missing.
    async with session_factory() as session:
        suite_report = await run_regression(session, run_id)
    assert suite_report.passed is False
    assert "spec_present_when_evaluation_present" in suite_report.failed_checks()


async def test_world_models_should_fail_invalid_accuracy(
    session_factory: async_sessionmaker, run_id: str
) -> None:
    """An evaluation artifact reporting accuracy=1.5 must trip the claim.

    Tests the unit-interval guard in I1: the falsifier flags the offending
    artifact and names the field whose value escaped [0, 1].
    """
    artifact_service = get_artifact_service()
    bogus_evaluation = {
        "model_id": "model_with_bad_accuracy",
        "counterfactual_accuracy": 1.5,
        "intervention_success_rate": 0.9,
        "causal_consistency_score": 0.8,
        "num_queries_tested": 3,
        "failed_queries": [],
        "evaluated_at": "2026-05-12T00:00:00+00:00",
    }
    async with session_factory() as session:
        record = await artifact_service.store_artifact(
            session=session,
            data=json.dumps(bogus_evaluation).encode(),
            artifact_type=ARTIFACT_TYPE_EVALUATION,
            created_by="test_promotion_should_fail",
            run_id=run_id,
        )
        await session.commit()
        bogus_id = record.id

    async with session_factory() as session:
        report = await run_falsification(session, run_id, registry=get_claim_registry())
    by_name = {a.claim_name: a for a in report.attempts}
    attempt = by_name[CLAIM_NAME]
    assert attempt.falsified is True
    assert attempt.evidence is not None
    assert attempt.evidence.offending_artifact_ids == (bogus_id,)
    assert "counterfactual_accuracy" in attempt.evidence.details
