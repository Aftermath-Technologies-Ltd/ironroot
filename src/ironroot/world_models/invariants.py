# Author: Bradley R. Kinnard
"""Phase 4 invariants for the ``world_models`` subsystem.

This module is the integration point that lets ``world_models`` graduate
from ``experimental`` to ``supported``. It registers:

* one ``FalsifiableClaim`` — ``world_models.evaluation_artifact_well_formed`` —
  asserting that every stored ``world_model_evaluation`` artifact for a run
  parses as a valid :class:`EvaluationReport` JSON, hashes to its declared
  ``content_hash``, and reports ``counterfactual_accuracy`` /
  ``intervention_success_rate`` / ``causal_consistency_score`` in ``[0, 1]``.
* one ``RegressionSuite`` keyed on ``run_kind="world_models_promotion"``
  with two checks: (a) every run with world-model artifacts has at least one
  spec, (b) every evaluation artifact references a known model_id present
  on the same run.

Registration is **idempotent** so re-importing ``ironroot.world_models`` is a
no-op for the registries. The audit (``ironroot-promote``) triggers
registration by importing the package.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from ironroot.storage.artifact_service import get_artifact_service
from ironroot.storage.models import ArtifactRecord

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
from ironroot.verification.falsification import (
    FalsifiableClaim,
    FalsificationAttempt,
    FalsificationEvidence,
    get_claim_registry,
)
from ironroot.verification.regression import (
    RegressionCheckResult,
    RegressionSuite,
    get_regression_registry,
)

CLAIM_NAME = "world_models.evaluation_artifact_well_formed"
SUITE_RUN_KIND = "world_models_promotion"
SUITE_NAME = "world_models_promotion_suite"

ARTIFACT_TYPE_SPEC = "world_model_spec"
ARTIFACT_TYPE_EVALUATION = "world_model_evaluation"

# Fields required on a serialised :class:`EvaluationReport`. Mirrors
# ``EvaluationReport.to_dict`` in ``world_models/__init__.py`` — keep in
# sync if that dataclass changes.
_REQUIRED_EVAL_FIELDS = (
    "model_id",
    "counterfactual_accuracy",
    "intervention_success_rate",
    "causal_consistency_score",
    "num_queries_tested",
    "failed_queries",
    "evaluated_at",
)


def _is_unit_interval(value: Any) -> bool:
    """True iff ``value`` is numeric and within ``[0.0, 1.0]``."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0.0 <= value <= 1.0


# ---------------------------------------------------------------------------
# Falsifier
# ---------------------------------------------------------------------------


async def _falsify_evaluation_artifact_well_formed(
    session: AsyncSession, run_id: str
) -> FalsificationAttempt:
    """Run the world-model evaluation well-formedness check for ``run_id``.

    Vacuously holds when the run has zero evaluation artifacts (the gate must
    not invent a failure where there's nothing to verify).
    """
    artifact_service = get_artifact_service()
    result = await session.execute(
        select(ArtifactRecord).where(
            ArtifactRecord.run_id == run_id,
            ArtifactRecord.artifact_type == ARTIFACT_TYPE_EVALUATION,
        )
    )
    artifacts = list(result.scalars().all())
    examined = len(artifacts)

    for artifact in artifacts:
        if not artifact_service.verify_integrity(artifact.content_hash):
            return FalsificationAttempt(
                claim_name=CLAIM_NAME,
                falsified=True,
                evidence=FalsificationEvidence(
                    offending_artifact_ids=(artifact.id,),
                    details=(
                        f"evaluation artifact id={artifact.id} "
                        f"content_hash={artifact.content_hash} failed integrity "
                        "verification (missing bytes or hash mismatch)"
                    ),
                ),
                method="ArtifactStore.verify + JSON well-formedness",
                rows_examined=examined,
            )

        try:
            payload = json.loads(artifact_service.retrieve_data(artifact.content_hash))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return FalsificationAttempt(
                claim_name=CLAIM_NAME,
                falsified=True,
                evidence=FalsificationEvidence(
                    offending_artifact_ids=(artifact.id,),
                    details=(
                        f"evaluation artifact id={artifact.id} does not decode "
                        f"as JSON: {type(exc).__name__}: {exc}"
                    ),
                ),
                method="ArtifactStore.verify + JSON well-formedness",
                rows_examined=examined,
            )

        if not isinstance(payload, dict):
            return FalsificationAttempt(
                claim_name=CLAIM_NAME,
                falsified=True,
                evidence=FalsificationEvidence(
                    offending_artifact_ids=(artifact.id,),
                    details=(
                        f"evaluation artifact id={artifact.id} decoded to "
                        f"{type(payload).__name__}, expected dict"
                    ),
                ),
                method="ArtifactStore.verify + JSON well-formedness",
                rows_examined=examined,
            )

        missing = [field for field in _REQUIRED_EVAL_FIELDS if field not in payload]
        if missing:
            return FalsificationAttempt(
                claim_name=CLAIM_NAME,
                falsified=True,
                evidence=FalsificationEvidence(
                    offending_artifact_ids=(artifact.id,),
                    details=(
                        f"evaluation artifact id={artifact.id} missing required "
                        f"fields: {missing}"
                    ),
                ),
                method="ArtifactStore.verify + JSON well-formedness",
                rows_examined=examined,
            )

        for unit_field in (
            "counterfactual_accuracy",
            "intervention_success_rate",
            "causal_consistency_score",
        ):
            if not _is_unit_interval(payload[unit_field]):
                return FalsificationAttempt(
                    claim_name=CLAIM_NAME,
                    falsified=True,
                    evidence=FalsificationEvidence(
                        offending_artifact_ids=(artifact.id,),
                        details=(
                            f"evaluation artifact id={artifact.id} field "
                            f"{unit_field}={payload[unit_field]!r} is outside [0, 1]"
                        ),
                    ),
                    method="ArtifactStore.verify + JSON well-formedness",
                    rows_examined=examined,
                )

    return FalsificationAttempt(
        claim_name=CLAIM_NAME,
        falsified=False,
        evidence=None,
        method="ArtifactStore.verify + JSON well-formedness",
        rows_examined=examined,
    )


# ---------------------------------------------------------------------------
# Regression checks
# ---------------------------------------------------------------------------


async def _check_spec_present_when_evaluation_present(
    session: AsyncSession, run_id: str
) -> RegressionCheckResult:
    """If a run has any evaluation artifact, it must also have ≥1 spec artifact.

    An evaluation report without a corresponding spec means the run produced
    output for a model the chain has no record of registering — a
    provenance break that the registry's :meth:`evaluate_model` would have
    raised had it been called against this run, so its presence here is a
    regression.
    """
    has_eval = (
        await session.execute(
            select(ArtifactRecord.id)
            .where(ArtifactRecord.run_id == run_id)
            .where(ArtifactRecord.artifact_type == ARTIFACT_TYPE_EVALUATION)
            .limit(1)
        )
    ).first()
    if has_eval is None:
        return RegressionCheckResult(
            check_name="spec_present_when_evaluation_present",
            passed=True,
            details="no evaluation artifacts on this run; check vacuous",
            rows_examined=0,
        )

    has_spec = (
        await session.execute(
            select(ArtifactRecord.id)
            .where(ArtifactRecord.run_id == run_id)
            .where(ArtifactRecord.artifact_type == ARTIFACT_TYPE_SPEC)
            .limit(1)
        )
    ).first()
    passed = has_spec is not None
    return RegressionCheckResult(
        check_name="spec_present_when_evaluation_present",
        passed=passed,
        details=("" if passed else "run has evaluation artifact(s) but no spec artifact"),
        rows_examined=1,
    )


async def _check_evaluation_references_known_spec(
    session: AsyncSession, run_id: str
) -> RegressionCheckResult:
    """Every evaluation artifact's ``model_id`` matches a spec on the same run.

    Reads both artifact sets, decodes each JSON payload, and asserts the
    ``model_id`` referenced by every evaluation appears in the spec set.
    Bad JSON is delegated to the falsifier above; this check treats
    undecodable payloads as failure with a pointer to the offending row.
    """
    artifact_service = get_artifact_service()
    spec_rows = list(
        (
            await session.execute(
                select(ArtifactRecord)
                .where(ArtifactRecord.run_id == run_id)
                .where(ArtifactRecord.artifact_type == ARTIFACT_TYPE_SPEC)
            )
        )
        .scalars()
        .all()
    )
    eval_rows = list(
        (
            await session.execute(
                select(ArtifactRecord)
                .where(ArtifactRecord.run_id == run_id)
                .where(ArtifactRecord.artifact_type == ARTIFACT_TYPE_EVALUATION)
            )
        )
        .scalars()
        .all()
    )

    known_model_ids: set[str] = set()
    for spec in spec_rows:
        try:
            payload = json.loads(artifact_service.retrieve_data(spec.content_hash))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("model_id"), str):
            known_model_ids.add(payload["model_id"])

    offending: list[str] = []
    for ev in eval_rows:
        try:
            payload = json.loads(artifact_service.retrieve_data(ev.content_hash))
        except (json.JSONDecodeError, UnicodeDecodeError):
            offending.append(ev.id)
            continue
        if not isinstance(payload, dict):
            offending.append(ev.id)
            continue
        model_id = payload.get("model_id")
        if not isinstance(model_id, str) or model_id not in known_model_ids:
            offending.append(ev.id)

    passed = not offending
    return RegressionCheckResult(
        check_name="evaluation_references_known_spec",
        passed=passed,
        details=(
            ""
            if passed
            else f"{len(offending)} evaluation artifact(s) reference unknown "
            f"model_ids: {offending}"
        ),
        rows_examined=len(eval_rows),
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


_CLAIM = FalsifiableClaim(
    name=CLAIM_NAME,
    description=(
        "Every world_model_evaluation artifact for a run parses as a valid "
        "EvaluationReport JSON, hashes to its declared content_hash, and "
        "reports the three accuracy metrics in [0, 1]."
    ),
    falsifier=_falsify_evaluation_artifact_well_formed,
)

_SUITE = RegressionSuite(
    name=SUITE_NAME,
    run_kind=SUITE_RUN_KIND,
    checks=(
        ("spec_present_when_evaluation_present", _check_spec_present_when_evaluation_present),
        ("evaluation_references_known_spec", _check_evaluation_references_known_spec),
    ),
)


def register_with_default_registries() -> None:
    """Register the world_models claim + suite. Idempotent.

    Called at package import time from ``ironroot.world_models``. Safe to
    call again — re-registration is a no-op rather than an error so tests
    that import the package multiple times don't blow up.
    """
    claim_reg = get_claim_registry()
    if claim_reg.get(CLAIM_NAME) is None:
        claim_reg.register(_CLAIM)

    suite_reg = get_regression_registry()
    if suite_reg.for_run_kind(SUITE_RUN_KIND) is None:
        suite_reg.register(_SUITE)


__all__ = [
    "ARTIFACT_TYPE_EVALUATION",
    "ARTIFACT_TYPE_SPEC",
    "CLAIM_NAME",
    "SUITE_NAME",
    "SUITE_RUN_KIND",
    "register_with_default_registries",
]
