# Author: Bradley R. Kinnard
"""Unit tests for the Phase 4 ``ironroot-promote`` audit CLI.

The audit is the durable mechanism the upgrade plan calls for in Phase 4:
each criterion has its own check, the rollup gates the exit code, and
``--json`` returns a stable shape suitable for piping into other tooling.

These tests deliberately operate against the real repo state. They are
not unit-test purists' tests — the audit's whole job is to inspect the
repository, so the test bed IS the repo.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ironroot.cli.promote import (
    Finding,
    PromotionReport,
    Severity,
    _check_experimental_status,
    _check_falsifiable_claim_registered,
    _check_invariants_doc,
    _check_no_random,
    _check_promotion_test_fixture,
    _check_regression_suite_registered,
    _check_subsystem_exists,
    _check_typed_belief_writes,
    _flat_name,
    audit,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _reregister_world_models_invariants() -> None:
    """Re-register the world_models claim + suite before each test.

    Phase 4 registries are process-global; other tests in this suite call
    ``reset_claim_registry_for_testing()`` to validate the empty-registry
    failure mode. Without this fixture the audit checks would see a
    half-populated registry depending on collection order.
    """
    from ironroot.world_models.invariants import register_with_default_registries

    register_with_default_registries()


# ---------------------------------------------------------------------------
# helpers + report rollup
# ---------------------------------------------------------------------------


def test_flat_name_handles_dotted_prefixes() -> None:
    assert _flat_name("world_models") == "world_models"
    assert _flat_name("cognition.planning") == "cognition_planning"
    assert _flat_name("a.b.c") == "a_b_c"


def test_report_rollup_picks_worst_severity() -> None:
    report = PromotionReport(prefix="x")
    report.add(Finding(check="a", severity=Severity.OK, message=""))
    assert report.worst == Severity.OK
    report.add(Finding(check="b", severity=Severity.WARN, message=""))
    assert report.worst == Severity.WARN
    report.add(Finding(check="c", severity=Severity.FAIL, message=""))
    assert report.worst == Severity.FAIL
    assert report.eligible is False
    assert report.exit_code() == 1


def test_report_exit_code_zero_when_no_fail() -> None:
    report = PromotionReport(prefix="x")
    report.add(Finding(check="a", severity=Severity.OK, message=""))
    report.add(Finding(check="b", severity=Severity.WARN, message=""))
    assert report.eligible is True
    assert report.exit_code() == 0


# ---------------------------------------------------------------------------
# subsystem.exists
# ---------------------------------------------------------------------------


def test_subsystem_exists_fail_for_unknown_prefix() -> None:
    finding = _check_subsystem_exists("this_does_not_exist_anywhere")
    assert finding.severity == Severity.FAIL


def test_subsystem_exists_ok_for_world_models() -> None:
    finding = _check_subsystem_exists("world_models")
    assert finding.severity == Severity.OK


# ---------------------------------------------------------------------------
# criterion 1 — no random
# ---------------------------------------------------------------------------


def test_no_random_passes_for_world_models() -> None:
    finding = _check_no_random("world_models")
    assert finding.severity == Severity.OK


def test_no_random_fails_for_cognition_strategies() -> None:
    """cognition.strategies uses ``random.*`` per EXPERIMENTAL.md."""
    finding = _check_no_random("cognition.strategies")
    assert finding.severity == Severity.FAIL
    assert "RNG reference" in finding.message


# ---------------------------------------------------------------------------
# criterion 2 — typed-belief writes
# ---------------------------------------------------------------------------


def test_typed_belief_writes_passes_for_world_models() -> None:
    """world_models writes no beliefs; trivially passes the typed-write check."""
    finding = _check_typed_belief_writes("world_models")
    assert finding.severity == Severity.OK


def test_typed_belief_writes_flags_free_form_create_belief(tmp_path: Path) -> None:
    """Concrete free-form belief writes must surface as FAIL.

    Constructs a throwaway subsystem at ``src/ironroot/_promote_fixture/``
    via ``monkeypatch`` would normally be ideal, but ``_check_typed_belief_writes``
    reads files off disk by dotted-prefix → fs-path mapping. Easier to
    direct the scan at a controlled path via the lower-level helper.
    """
    from ironroot.cli.promote import _RAW_BELIEF_WRITE_PATTERNS, _scan_for_patterns

    fixture = tmp_path / "freeform.py"
    fixture.write_text("service.create_belief(metric_class=MetricClass.PRIMARY)\n")
    hits = _scan_for_patterns(tmp_path, _RAW_BELIEF_WRITE_PATTERNS)
    assert hits, "scanner must flag a free-form create_belief call"


# ---------------------------------------------------------------------------
# criterion 3 — falsifiable claim
# ---------------------------------------------------------------------------


def test_falsifiable_claim_passes_for_world_models() -> None:
    """Importing world_models registers its claim; check should find it."""
    finding = _check_falsifiable_claim_registered("world_models")
    assert finding.severity == Severity.OK
    assert "world_models.evaluation_artifact_well_formed" in finding.message


def test_falsifiable_claim_fails_for_agents() -> None:
    """No ``agents.*`` claim is registered, so this must FAIL."""
    finding = _check_falsifiable_claim_registered("agents")
    assert finding.severity == Severity.FAIL
    assert "no FalsifiableClaim" in finding.message


# ---------------------------------------------------------------------------
# criterion 4a — regression suite registered
# ---------------------------------------------------------------------------


def test_regression_suite_passes_for_world_models() -> None:
    finding = _check_regression_suite_registered("world_models")
    assert finding.severity == Severity.OK
    assert "world_models_promotion" in finding.message


def test_regression_suite_fails_for_agi() -> None:
    finding = _check_regression_suite_registered("agi")
    assert finding.severity == Severity.FAIL


# ---------------------------------------------------------------------------
# criterion 4b — promotion test fixture
# ---------------------------------------------------------------------------


def test_promotion_fixtures_pass_for_world_models() -> None:
    finding = _check_promotion_test_fixture("world_models")
    assert finding.severity == Severity.OK


def test_promotion_fixtures_fail_when_file_absent() -> None:
    finding = _check_promotion_test_fixture("evolution")
    assert finding.severity == Severity.FAIL
    assert "no promotion test file" in finding.message


# ---------------------------------------------------------------------------
# criterion 5 — invariants doc
# ---------------------------------------------------------------------------


def test_invariants_doc_passes_for_world_models() -> None:
    finding = _check_invariants_doc("world_models")
    assert finding.severity == Severity.OK


def test_invariants_doc_fails_when_missing() -> None:
    finding = _check_invariants_doc("evolution")
    assert finding.severity == Severity.FAIL


# ---------------------------------------------------------------------------
# experimental status (informational)
# ---------------------------------------------------------------------------


def test_experimental_status_ok_for_promoted_subsystem() -> None:
    """world_models was removed from EXPERIMENTAL_MODULE_PREFIXES."""
    finding = _check_experimental_status("world_models")
    assert finding.severity == Severity.OK


def test_experimental_status_warn_for_still_quarantined() -> None:
    finding = _check_experimental_status("agi")
    assert finding.severity == Severity.WARN


# ---------------------------------------------------------------------------
# end-to-end audit driver
# ---------------------------------------------------------------------------


def test_audit_world_models_is_fully_eligible() -> None:
    """The Phase 4 closeout claim: world_models audits clean.

    This test is the load-bearing closeout assertion — if it fails, the
    promotion regressed.
    """
    report = audit("world_models")
    failures = [f for f in report.findings if f.severity == Severity.FAIL]
    assert failures == [], f"expected zero FAIL findings, got: {failures}"
    assert report.eligible is True
    assert report.exit_code() == 0


def test_audit_unknown_subsystem_short_circuits() -> None:
    """A bogus prefix should produce a single FAIL on subsystem.exists."""
    report = audit("definitely_not_a_real_subsystem_xyz")
    assert len(report.findings) == 1
    assert report.findings[0].check == "subsystem.exists"
    assert report.findings[0].severity == Severity.FAIL


def test_audit_still_quarantined_subsystem_has_failures() -> None:
    """An untouched experimental subsystem must accumulate FAILs.

    Picks ``agi`` — large RNG-driven simulation surface; no claim, no
    suite, no invariants doc, no promotion fixture.
    """
    report = audit("agi")
    assert report.eligible is False
    assert report.exit_code() == 1
    failures = {f.check for f in report.findings if f.severity == Severity.FAIL}
    expected_failures = {
        "criterion_1.no_random",
        "criterion_3.falsifiable_claim",
        "criterion_4a.regression_suite",
        "criterion_4b.promotion_fixtures",
        "criterion_5.invariants_doc",
    }
    assert expected_failures.issubset(
        failures
    ), f"missing expected failures: {expected_failures - failures}"


# ---------------------------------------------------------------------------
# CLI entrypoint (subprocess so we exercise the argparse + exit code path)
# ---------------------------------------------------------------------------


def test_cli_world_models_returns_zero() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ironroot.cli.promote", "world_models"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "worst: OK" in result.stdout
    assert "eligible: True" in result.stdout


def test_cli_emits_json_with_stable_shape() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ironroot.cli.promote", "--json", "world_models"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["prefix"] == "world_models"
    assert payload["worst"] == "ok"
    assert payload["eligible"] is True
    assert isinstance(payload["findings"], list) and payload["findings"]
    for f in payload["findings"]:
        assert set(f.keys()) >= {"check", "severity", "message"}


def test_cli_list_enumerates_experimental_prefixes() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ironroot.cli.promote", "--list"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "experimental subsystem prefixes:" in result.stdout
    # The promoted graduate must NOT appear in the experimental list.
    assert "world_models" not in result.stdout
    assert "- agi" in result.stdout


def test_cli_requires_prefix_or_list() -> None:
    """No args + no --list = argparse error (exit 2)."""
    result = subprocess.run(
        [sys.executable, "-m", "ironroot.cli.promote"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
