# Author: Bradley R. Kinnard
"""``ironroot-promote`` — Phase 4 promotion audit CLI.

Given an experimental subsystem prefix (e.g. ``world_models``), audit it
against the five promotion criteria in
``upgrade-plan.md`` Phase 4 / ``EXPERIMENTAL.md``:

1. No ``random.*`` / ``numpy.random.*`` in any non-test path of the subsystem.
2. Writes only typed beliefs with real provenance (i.e. no free-form
   ``MetricClass`` strings or direct ``BeliefService.create_belief`` calls).
3. At least one ``FalsifiableClaim`` registered with the falsification gate,
   namespaced ``<subsystem>.*``.
4. A regression suite registered for ``run_kind == "<subsystem>_promotion"``,
   plus a promotion test fixture file at
   ``tests/promotion/test_<flat-subsystem>_promotion.py`` whose name signals
   both should-pass and should-fail cases.
5. Invariants documentation at ``docs/invariants/<flat-subsystem>.md`` exists
   and is non-empty.

The CLI emits a human-readable table by default and JSON with ``--json``.
Exit code is 1 if any ``FAIL`` finding is present, 0 otherwise. ``WARN``
does not gate the exit code so this can be wired into CI as a build guard.

The audit is **declarative**: it does NOT auto-flip ``EXPERIMENTAL.md`` or
mutate ``EXPERIMENTAL_MODULE_PREFIXES``. Promotion is a deliberate operator
action — the audit only verifies eligibility.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src" / "ironroot"
TESTS_PROMOTION_ROOT = REPO_ROOT / "tests" / "promotion"
DOCS_INVARIANTS_ROOT = REPO_ROOT / "docs" / "invariants"


class Severity(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True)
class Finding:
    """One promotion check's outcome."""

    check: str
    severity: Severity
    message: str
    recommendation: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class PromotionReport:
    """Aggregate audit result for one subsystem."""

    prefix: str
    findings: list[Finding] = field(default_factory=list)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    @property
    def worst(self) -> Severity:
        if any(f.severity == Severity.FAIL for f in self.findings):
            return Severity.FAIL
        if any(f.severity == Severity.WARN for f in self.findings):
            return Severity.WARN
        return Severity.OK

    @property
    def eligible(self) -> bool:
        """Subsystem is eligible for promotion iff there are no FAIL findings."""
        return self.worst != Severity.FAIL

    def exit_code(self) -> int:
        return 1 if self.worst == Severity.FAIL else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "prefix": self.prefix,
            "worst": str(self.worst),
            "eligible": self.eligible,
            "findings": [asdict(f) for f in self.findings],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flat_name(prefix: str) -> str:
    """``cognition.planning`` -> ``cognition_planning``; ``world_models`` unchanged."""
    return prefix.replace(".", "_")


def _subsystem_src_root(prefix: str) -> Path:
    """Map a dotted module prefix to its filesystem root under ``src/ironroot/``."""
    return SRC_ROOT.joinpath(*prefix.split("."))


_RNG_PATTERNS = (
    re.compile(r"\brandom\.[A-Za-z_]"),
    re.compile(r"\bnumpy\.random\b"),
    re.compile(r"\bnp\.random\b"),
    re.compile(r"\bfrom\s+random\s+import\b"),
    re.compile(r"\bfrom\s+numpy\.random\s+import\b"),
    re.compile(r"^\s*import\s+random\s*(?:#|$)", re.MULTILINE),
    re.compile(r"^\s*import\s+numpy\.random\s*(?:#|$)", re.MULTILINE),
)
_TRIPLE_QUOTED = re.compile(r"(?s)(\"\"\".*?\"\"\"|'''.*?''')")
_LINE_COMMENT = re.compile(r"#.*?$", re.MULTILINE)


def _scan_for_patterns(
    src_dir: Path, patterns: tuple[re.Pattern[str], ...]
) -> list[tuple[Path, int, str]]:
    """Scan every ``*.py`` file under ``src_dir`` for any matching pattern.

    Triple-quoted strings and ``#`` comments are stripped before matching so
    docstrings / examples don't false-positive.
    """
    hits: list[tuple[Path, int, str]] = []
    if not src_dir.exists():
        return hits
    paths = [src_dir] if src_dir.is_file() else sorted(src_dir.rglob("*.py"))
    for path in paths:
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        cleaned = _TRIPLE_QUOTED.sub("", text)
        cleaned = _LINE_COMMENT.sub("", cleaned)
        for lineno, line in enumerate(cleaned.splitlines(), start=1):
            for pat in patterns:
                if pat.search(line):
                    hits.append((path, lineno, line.strip()))
                    break
    return hits


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_subsystem_exists(prefix: str) -> Finding:
    """Sanity gate: the subsystem must actually exist on disk."""
    src_dir = _subsystem_src_root(prefix)
    if not src_dir.exists():
        return Finding(
            check="subsystem.exists",
            severity=Severity.FAIL,
            message=f"no source tree at {src_dir.relative_to(REPO_ROOT)}",
            recommendation=(
                "pass a dotted prefix that matches a directory or module under " "src/ironroot/"
            ),
        )
    return Finding(
        check="subsystem.exists",
        severity=Severity.OK,
        message=f"source tree at {src_dir.relative_to(REPO_ROOT)}",
    )


def _check_no_random(prefix: str) -> Finding:
    """Criterion #1: no ``random.*`` / ``numpy.random.*`` in the subsystem tree."""
    src_dir = _subsystem_src_root(prefix)
    hits = _scan_for_patterns(src_dir, _RNG_PATTERNS)
    if hits:
        details = [f"{p.relative_to(REPO_ROOT)}:{lineno}: {line}" for p, lineno, line in hits[:10]]
        return Finding(
            check="criterion_1.no_random",
            severity=Severity.FAIL,
            message=f"found {len(hits)} RNG reference(s) in subsystem tree",
            recommendation=(
                "replace RNG with a deterministic fixture (see "
                "verification/fault_fixtures.py for the pattern)"
            ),
            details={"hits": details},
        )
    return Finding(
        check="criterion_1.no_random",
        severity=Severity.OK,
        message="no RNG references in subsystem tree",
    )


# Free-form belief-write patterns that promoted subsystems are NOT allowed
# to use. The typed API (``append_observation`` / ``append_inference`` /
# ``append_gate_result``) routes through the same canonical service but
# enforces typed kwargs and provenance.
_RAW_BELIEF_WRITE_PATTERNS = (
    re.compile(r"\.create_belief\s*\("),
    re.compile(r"\._create_belief\s*\("),
    re.compile(r"MetricClass\.PRIMARY"),
)


def _check_typed_belief_writes(prefix: str) -> Finding:
    """Criterion #2: writes only typed beliefs with real provenance.

    A subsystem either (a) writes no beliefs at all (vacuously passes), or
    (b) uses ``BeliefService.append_observation`` / ``append_inference`` /
    ``append_gate_result`` exclusively. Direct ``create_belief`` calls and
    free-form ``MetricClass.PRIMARY`` references are forbidden.

    Provenance itself is enforced at the DB layer by the
    ``ck_beliefs_provenance_for_derived`` CHECK constraint added in
    Phase 2c.3, so this audit only catches the call-site shape.
    """
    src_dir = _subsystem_src_root(prefix)
    hits = _scan_for_patterns(src_dir, _RAW_BELIEF_WRITE_PATTERNS)
    if hits:
        details = [f"{p.relative_to(REPO_ROOT)}:{lineno}: {line}" for p, lineno, line in hits[:10]]
        return Finding(
            check="criterion_2.typed_belief_writes",
            severity=Severity.FAIL,
            message=f"found {len(hits)} free-form belief write(s); use the typed API",
            recommendation=(
                "replace .create_belief / MetricClass.PRIMARY with "
                "service.append_observation / append_inference / "
                "append_gate_result and pass a ProvenanceRef"
            ),
            details={"hits": details},
        )
    return Finding(
        check="criterion_2.typed_belief_writes",
        severity=Severity.OK,
        message="no free-form belief writes in subsystem tree",
    )


def _ensure_subsystem_registered(prefix: str) -> Exception | None:
    """Import the subsystem and (idempotently) call its ``invariants`` hook.

    Phase 4 convention: every promoted subsystem ships an ``invariants``
    submodule that exposes ``register_with_default_registries() -> None``.
    The audit calls it explicitly so the check survives the registry-reset
    helpers in the falsification and regression modules — without this hook,
    a test that calls ``reset_claim_registry_for_testing()`` earlier in the
    pytest session would wipe a subsystem's claim and the audit would then
    report a false FAIL.
    """
    try:
        importlib.import_module(f"ironroot.{prefix}")
    except Exception as exc:
        return exc
    try:
        invariants_mod = importlib.import_module(f"ironroot.{prefix}.invariants")
    except ModuleNotFoundError:
        return None
    except Exception as exc:
        return exc
    hook = getattr(invariants_mod, "register_with_default_registries", None)
    if callable(hook):
        try:
            hook()
        except Exception as exc:
            return exc
    return None


def _check_falsifiable_claim_registered(prefix: str) -> Finding:
    """Criterion #3: at least one ``FalsifiableClaim`` namespaced ``<prefix>.*``.

    Imports the subsystem to trigger side-effecting claim registration, then
    queries the process-global registry.
    """
    err = _ensure_subsystem_registered(prefix)
    if err is not None:
        return Finding(
            check="criterion_3.falsifiable_claim",
            severity=Severity.FAIL,
            message=f"importing ironroot.{prefix} raised {type(err).__name__}: {err}",
            recommendation=(
                "ensure ``ironroot.<prefix>`` is importable without side effects "
                "beyond claim/suite registration"
            ),
        )

    from ironroot.verification.falsification import get_claim_registry

    registry = get_claim_registry()
    matching = [
        name for name in registry.names() if name == prefix or name.startswith(prefix + ".")
    ]
    if not matching:
        return Finding(
            check="criterion_3.falsifiable_claim",
            severity=Severity.FAIL,
            message=f"no FalsifiableClaim namespaced 'ironroot.{prefix}.*' is registered",
            recommendation=(
                "register a FalsifiableClaim via ironroot.verification.falsification."
                "get_claim_registry().register(...) at subsystem import time, with "
                f"name='{prefix}.<your_claim>'"
            ),
        )
    return Finding(
        check="criterion_3.falsifiable_claim",
        severity=Severity.OK,
        message=f"{len(matching)} claim(s) registered: {sorted(matching)}",
        details={"claims": sorted(matching)},
    )


def _check_regression_suite_registered(prefix: str) -> Finding:
    """Criterion #4a: a ``RegressionSuite`` registered for ``run_kind=<prefix>_promotion``."""
    err = _ensure_subsystem_registered(prefix)
    if err is not None:
        return Finding(
            check="criterion_4a.regression_suite",
            severity=Severity.FAIL,
            message=f"importing ironroot.{prefix} raised {type(err).__name__}: {err}",
        )

    from ironroot.verification.regression import get_regression_registry

    run_kind = f"{_flat_name(prefix)}_promotion"
    registry = get_regression_registry()
    suite = registry.for_run_kind(run_kind)
    if suite is None:
        return Finding(
            check="criterion_4a.regression_suite",
            severity=Severity.FAIL,
            message=f"no RegressionSuite registered for run_kind='{run_kind}'",
            recommendation=(
                "register a RegressionSuite via ironroot.verification.regression."
                f"get_regression_registry().register(...) with run_kind='{run_kind}' "
                "at subsystem import time"
            ),
        )
    return Finding(
        check="criterion_4a.regression_suite",
        severity=Severity.OK,
        message=f"suite '{suite.name}' registered for run_kind='{run_kind}' "
        f"with {len(suite.checks)} check(s)",
        details={"run_kind": run_kind, "suite_name": suite.name, "check_count": len(suite.checks)},
    )


def _check_promotion_test_fixture(prefix: str) -> Finding:
    """Criterion #4b: should-fail + should-pass fixtures live in a promotion test file.

    The convention is one file at
    ``tests/promotion/test_<flat_prefix>_promotion.py`` that contains both
    ``def test_*should_pass*`` and ``def test_*should_fail*`` cases. The
    audit only checks the file exists and names match the convention; the
    actual pass/fail semantics are verified by ``pytest`` running those
    tests.
    """
    flat = _flat_name(prefix)
    test_file = TESTS_PROMOTION_ROOT / f"test_{flat}_promotion.py"
    if not test_file.exists():
        return Finding(
            check="criterion_4b.promotion_fixtures",
            severity=Severity.FAIL,
            message=f"no promotion test file at {test_file.relative_to(REPO_ROOT)}",
            recommendation=(
                "create tests/promotion/test_<subsystem>_promotion.py with at "
                "least one should-pass and one should-fail test case exercising "
                "the registered regression suite"
            ),
        )
    text = test_file.read_text(encoding="utf-8")
    has_pass = re.search(r"def\s+test_\w*should_pass\w*\s*\(", text) is not None
    has_fail = re.search(r"def\s+test_\w*should_fail\w*\s*\(", text) is not None
    missing: list[str] = []
    if not has_pass:
        missing.append("test_*should_pass*")
    if not has_fail:
        missing.append("test_*should_fail*")
    if missing:
        return Finding(
            check="criterion_4b.promotion_fixtures",
            severity=Severity.FAIL,
            message=f"{test_file.relative_to(REPO_ROOT)} missing: {missing}",
            recommendation=(
                "name the cases so the audit can detect them: "
                "e.g. ``def test_world_models_should_pass(...)`` and "
                "``def test_world_models_should_fail(...)``"
            ),
        )
    return Finding(
        check="criterion_4b.promotion_fixtures",
        severity=Severity.OK,
        message=f"{test_file.relative_to(REPO_ROOT)} has should-pass + should-fail cases",
    )


def _check_invariants_doc(prefix: str) -> Finding:
    """Criterion #5: ``docs/invariants/<flat_prefix>.md`` exists and is non-empty."""
    flat = _flat_name(prefix)
    doc = DOCS_INVARIANTS_ROOT / f"{flat}.md"
    if not doc.exists():
        return Finding(
            check="criterion_5.invariants_doc",
            severity=Severity.FAIL,
            message=f"no invariants doc at {doc.relative_to(REPO_ROOT)}",
            recommendation=(
                f"author docs/invariants/{flat}.md listing the subsystem's "
                "documented invariants, their falsifiers, and how each can fail"
            ),
        )
    if doc.stat().st_size == 0:
        return Finding(
            check="criterion_5.invariants_doc",
            severity=Severity.FAIL,
            message=f"{doc.relative_to(REPO_ROOT)} is empty",
        )
    return Finding(
        check="criterion_5.invariants_doc",
        severity=Severity.OK,
        message=f"{doc.relative_to(REPO_ROOT)} present ({doc.stat().st_size} bytes)",
    )


def _check_experimental_status(prefix: str) -> Finding:
    """Informational: is ``prefix`` still in ``EXPERIMENTAL_MODULE_PREFIXES``?

    The audit does NOT auto-flip the manifest. If every other check is OK
    and the prefix is still listed, this is a ``WARN`` reminding the operator
    to remove it and flip ``EXPERIMENTAL.md``. If the prefix is already
    removed, this is ``OK``.
    """
    from ironroot.experimental import EXPERIMENTAL_MODULE_PREFIXES

    if prefix in EXPERIMENTAL_MODULE_PREFIXES:
        return Finding(
            check="status.experimental_manifest",
            severity=Severity.WARN,
            message=(
                f"'{prefix}' still listed in EXPERIMENTAL_MODULE_PREFIXES; "
                "remove it and flip EXPERIMENTAL.md once every FAIL is cleared"
            ),
            recommendation=(
                "edit src/ironroot/experimental/__init__.py to drop the entry, "
                "then update EXPERIMENTAL.md from 'experimental' to 'supported'"
            ),
        )
    return Finding(
        check="status.experimental_manifest",
        severity=Severity.OK,
        message=f"'{prefix}' is no longer in EXPERIMENTAL_MODULE_PREFIXES",
    )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def audit(prefix: str) -> PromotionReport:
    """Run every promotion check against ``prefix`` and return a report."""
    report = PromotionReport(prefix=prefix)
    sanity = _check_subsystem_exists(prefix)
    report.add(sanity)
    if sanity.severity == Severity.FAIL:
        return report
    report.add(_check_no_random(prefix))
    report.add(_check_typed_belief_writes(prefix))
    report.add(_check_falsifiable_claim_registered(prefix))
    report.add(_check_regression_suite_registered(prefix))
    report.add(_check_promotion_test_fixture(prefix))
    report.add(_check_invariants_doc(prefix))
    report.add(_check_experimental_status(prefix))
    return report


def _render_table(report: PromotionReport) -> str:
    rows = ["", f"PROMOTION AUDIT — ironroot.{report.prefix}", "=" * 72, ""]
    width = max((len(f.check) for f in report.findings), default=10)
    for f in report.findings:
        rows.append(f"  [{f.severity.value.upper():4}] {f.check:<{width}}  {f.message}")
        if f.recommendation:
            rows.append(f"          → {f.recommendation}")
    rows.append("")
    rows.append(f"  worst: {report.worst.value.upper()}  eligible: {report.eligible}")
    rows.append("")
    return "\n".join(rows)


def _list_experimental() -> str:
    from ironroot.experimental import EXPERIMENTAL_MODULE_PREFIXES

    lines = ["", "experimental subsystem prefixes:", ""]
    for p in EXPERIMENTAL_MODULE_PREFIXES:
        lines.append(f"  - {p}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ironroot-promote",
        description=(
            "Audit a quarantined subsystem against the Phase 4 promotion criteria. "
            "See upgrade-plan.md Phase 4 and EXPERIMENTAL.md."
        ),
    )
    parser.add_argument(
        "prefix",
        nargs="?",
        help="dotted subsystem prefix to audit, e.g. 'world_models' or 'cognition.planning'",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list every currently experimental subsystem and exit",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the audit report as JSON instead of a table",
    )
    args = parser.parse_args(argv)

    if args.list:
        sys.stdout.write(_list_experimental())
        return 0

    if not args.prefix:
        parser.error("a subsystem prefix is required (or pass --list)")

    report = audit(args.prefix)
    if args.json:
        sys.stdout.write(json.dumps(report.to_dict(), indent=2) + "\n")
    else:
        sys.stdout.write(_render_table(report))
    return report.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
