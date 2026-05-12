# Author: Bradley R. Kinnard
"""Regression suite registry (Phase 2a.2).

A *regression suite* is a named, ordered list of ``RegressionCheck``s
that the gate runs against a completed run. The suite passes only when
every check produces ``RegressionCheckResult(passed=True, …)`` AND no
new ``IncidentRecord`` rows were created during the run. Both halves are
required: an empty-incidents pass without check execution is the bug the
old gate had.

Suites are keyed by *run kind*. A run's kind is the string in
``RunRecord.config['run_kind']`` if present, falling back to
``"default"``. The registry is process-global so subsystems can add
suites at import time; tests can replace the singleton.

Each check is an async callable
``(session, run_id) -> RegressionCheckResult``. Checks MUST be
deterministic and MUST NOT mutate the DB. They MAY read any rows they
need to make their assertion.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.storage.models import BeliefRecord, IncidentRecord, RunRecord


@dataclass(frozen=True)
class RegressionCheckResult:
    """outcome of a single regression check."""

    check_name: str
    passed: bool
    details: str = ""
    rows_examined: int = 0
    offending_belief_ids: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_name": self.check_name,
            "passed": self.passed,
            "details": self.details,
            "rows_examined": self.rows_examined,
            "offending_belief_ids": list(self.offending_belief_ids),
        }


RegressionCheck = Callable[[AsyncSession, str], Awaitable[RegressionCheckResult]]


@dataclass(frozen=True)
class RegressionSuite:
    """ordered list of named regression checks for one run kind."""

    name: str
    run_kind: str
    checks: tuple[tuple[str, RegressionCheck], ...]


@dataclass(frozen=True)
class RegressionReport:
    """aggregate suite outcome — gate consumes this."""

    suite_name: str
    run_kind: str
    results: tuple[RegressionCheckResult, ...]
    incident_count: int

    @property
    def all_checks_passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def passed(self) -> bool:
        """suite passes iff every check passes AND no incidents fired.

        Either half failing is a regression — empty-incidents alone is
        not a free pass.
        """
        return self.all_checks_passed and self.incident_count == 0

    def failed_checks(self) -> tuple[str, ...]:
        return tuple(r.check_name for r in self.results if not r.passed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "run_kind": self.run_kind,
            "passed": self.passed,
            "all_checks_passed": self.all_checks_passed,
            "incident_count": self.incident_count,
            "failed_checks": list(self.failed_checks()),
            "results": [r.to_dict() for r in self.results],
        }


class RegressionSuiteRegistry:
    """maps run_kind -> RegressionSuite."""

    def __init__(self) -> None:
        self._suites: dict[str, RegressionSuite] = {}

    def register(self, suite: RegressionSuite) -> None:
        if suite.run_kind in self._suites:
            raise ValueError(f"suite already registered for run_kind={suite.run_kind}")
        self._suites[suite.run_kind] = suite

    def unregister(self, run_kind: str) -> None:
        self._suites.pop(run_kind, None)

    def for_run_kind(self, run_kind: str) -> RegressionSuite | None:
        return self._suites.get(run_kind)

    def kinds(self) -> tuple[str, ...]:
        return tuple(self._suites.keys())


# ---------------------------------------------------------------------------
# Builtin checks for the default suite
# ---------------------------------------------------------------------------


async def _check_chain_is_non_empty(session: AsyncSession, run_id: str) -> RegressionCheckResult:
    """a completed run must have at least the run_start lifecycle belief.

    An empty chain after a "completed" run is a regression: either the
    executor didn't actually run, or its writes were never committed.
    """
    result = await session.execute(select(BeliefRecord.id).where(BeliefRecord.run_id == run_id))
    rows = list(result.all())
    n = len(rows)
    return RegressionCheckResult(
        check_name="chain_is_non_empty",
        passed=n > 0,
        details="" if n > 0 else "completed run produced zero belief rows",
        rows_examined=n,
    )


async def _check_seq_starts_at_one(session: AsyncSession, run_id: str) -> RegressionCheckResult:
    """the chain root must be seq=1.

    A run whose first row is seq != 1 indicates either backfill drift
    (pre-Phase-1.1 data) or that someone wrote rows without going
    through ``BeliefService``.
    """
    row = (
        await session.execute(
            select(BeliefRecord.id, BeliefRecord.seq)
            .where(BeliefRecord.run_id == run_id)
            .order_by(BeliefRecord.seq.asc())
            .limit(1)
        )
    ).first()

    if row is None:
        return RegressionCheckResult(
            check_name="seq_starts_at_one",
            passed=False,
            details="no rows to check",
            rows_examined=0,
        )

    passed = row.seq == 1
    return RegressionCheckResult(
        check_name="seq_starts_at_one",
        passed=passed,
        details="" if passed else f"first row has seq={row.seq}",
        rows_examined=1,
        offending_belief_ids=() if passed else (row.id,),
    )


async def _check_no_orphaned_violation_beliefs(
    session: AsyncSession, run_id: str
) -> RegressionCheckResult:
    """every VIOLATION belief must reference a known invariant name.

    The invariants gate emits VIOLATION beliefs with ``content.invariant``
    set to a name from ``domain.invariants``. A violation without a
    recognizable invariant name suggests free-form writes from a code
    path that hasn't been migrated to the typed API.
    """
    from ironroot.domain.invariants import (
        ARTIFACT_INTEGRITY,
        BELIEF_HASH_CHAIN,
        BUDGET_NOT_NEGATIVE,
        RUN_STATE_MACHINE,
    )

    known = {
        ARTIFACT_INTEGRITY.name,
        BELIEF_HASH_CHAIN.name,
        BUDGET_NOT_NEGATIVE.name,
        RUN_STATE_MACHINE.name,
    }

    result = await session.execute(
        select(BeliefRecord.id, BeliefRecord.content)
        .where(BeliefRecord.run_id == run_id)
        .where(BeliefRecord.belief_type == "violation")
    )
    rows = list(result.all())
    bad: list[str] = []
    for row in rows:
        name = (row.content or {}).get("invariant")
        if name not in known:
            bad.append(row.id)

    return RegressionCheckResult(
        check_name="no_orphaned_violation_beliefs",
        passed=not bad,
        details="" if not bad else f"violation beliefs name unknown invariants: {bad}",
        rows_examined=len(rows),
        offending_belief_ids=tuple(bad),
    )


_DEFAULT_SUITE = RegressionSuite(
    name="default_chain_suite",
    run_kind="default",
    checks=(
        ("chain_is_non_empty", _check_chain_is_non_empty),
        ("seq_starts_at_one", _check_seq_starts_at_one),
        ("no_orphaned_violation_beliefs", _check_no_orphaned_violation_beliefs),
    ),
)


_registry: RegressionSuiteRegistry | None = None


def get_regression_registry() -> RegressionSuiteRegistry:
    """returns the process-global suite registry with the default suite preloaded."""
    global _registry
    if _registry is None:
        _registry = RegressionSuiteRegistry()
        _registry.register(_DEFAULT_SUITE)
    return _registry


def reset_regression_registry_for_testing() -> None:
    global _registry
    _registry = None


async def run_regression(
    session: AsyncSession,
    run_id: str,
    registry: RegressionSuiteRegistry | None = None,
) -> RegressionReport:
    """runs the registered regression suite + counts incidents.

    Resolves the suite via the run's ``config['run_kind']`` (default
    ``"default"``). If no suite is registered for the kind, raises
    ``ValueError("no_suite_for_run_kind:<kind>")`` — same logic as
    falsification: a regression gate with no suite must NOT be a free
    pass.
    """
    reg = registry or get_regression_registry()

    run = (
        await session.execute(select(RunRecord).where(RunRecord.id == run_id))
    ).scalar_one_or_none()
    run_kind = "default"
    if run is not None:
        cfg = run.config or {}
        run_kind = str(cfg.get("run_kind", "default"))

    suite = reg.for_run_kind(run_kind)
    if suite is None:
        raise ValueError(f"no_suite_for_run_kind:{run_kind}")

    results: list[RegressionCheckResult] = []
    for _, check in suite.checks:
        results.append(await check(session, run_id))

    incident_count = (
        await session.execute(select(IncidentRecord).where(IncidentRecord.run_id == run_id))
    ).scalars()
    incident_count_value = len(list(incident_count))

    return RegressionReport(
        suite_name=suite.name,
        run_kind=run_kind,
        results=tuple(results),
        incident_count=incident_count_value,
    )
