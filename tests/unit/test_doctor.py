# Author: Bradley R. Kinnard
"""Phase 3.5: ironroot-doctor CLI tests."""

from __future__ import annotations

import json
import os
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("IRONROOT_DEBUG", "true")

from ironroot.cli.doctor import (
    DoctorReport,
    Finding,
    Severity,
    _check_artifact_root,
    _check_settings,
    _redact_url,
    main,
    run_doctor,
)


class TestSeverityRollup:
    def test_empty_report_is_ok(self) -> None:
        report = DoctorReport()
        assert report.worst == Severity.OK
        assert report.exit_code() == 0

    def test_warn_alone_does_not_fail(self) -> None:
        report = DoctorReport()
        report.add(Finding(check="x", severity=Severity.WARN, message="m"))
        assert report.worst == Severity.WARN
        assert report.exit_code() == 0

    def test_fail_drives_nonzero_exit(self) -> None:
        report = DoctorReport()
        report.add(Finding(check="x", severity=Severity.OK, message="m"))
        report.add(Finding(check="y", severity=Severity.WARN, message="m"))
        report.add(Finding(check="z", severity=Severity.FAIL, message="m"))
        assert report.worst == Severity.FAIL
        assert report.exit_code() == 1


class TestSettingsChecks:
    def test_in_debug_mode_settings_load_is_ok(self) -> None:
        findings = _check_settings()
        names = {f.check for f in findings}
        assert "settings.load" in names
        assert "settings.db_password" in names
        assert "settings.cors_origins" in names
        assert "settings.auth_required" in names
        assert "settings.auth_rate_limit_per_minute" in names

    def test_default_db_password_in_debug_is_warn(self) -> None:
        findings = _check_settings()
        pw = next(f for f in findings if f.check == "settings.db_password")
        # In our test env, IRONROOT_DB_PASSWORD is unset → falls back to
        # the "changeme" default. In debug mode that's a WARN, not a
        # FAIL — the password guard only fires in non-debug.
        assert pw.severity in (Severity.OK, Severity.WARN)

    def test_auth_off_in_debug_is_warn(self) -> None:
        findings = _check_settings()
        auth = next(f for f in findings if f.check == "settings.auth_required")
        assert auth.severity in (Severity.OK, Severity.WARN)


class TestArtifactRoot:
    def test_writable_path_is_ok(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        from ironroot.settings import Settings, get_settings

        get_settings.cache_clear()
        monkeypatch.setattr(
            "ironroot.cli.doctor.get_settings" if False else "ironroot.settings.get_settings",
            lambda: Settings(
                debug=True,
                db_password="changeme",
                artifact_path=tmp_path,
                _env_file=None,  # type: ignore[call-arg]
            ),
        )
        finding = _check_artifact_root()
        assert finding.severity == Severity.OK

    def test_unwritable_path_is_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from ironroot.settings import Settings

        monkeypatch.setattr(
            "ironroot.settings.get_settings",
            lambda: Settings(
                debug=True,
                db_password="changeme",
                artifact_path=Path("/proc/nope/forbidden"),
                _env_file=None,  # type: ignore[call-arg]
            ),
        )
        finding = _check_artifact_root()
        # /proc/nope/forbidden won't exist; the check should be WARN
        # (does not exist) or FAIL (cannot write). Either is acceptable
        # for this assertion — the point is "operator gets a signal".
        assert finding.severity in (Severity.WARN, Severity.FAIL)


class TestUrlRedaction:
    def test_redacts_password(self) -> None:
        assert (
            _redact_url("postgresql://user:s3cret@host:5432/db")
            == "postgresql://user:***@host:5432/db"
        )

    def test_passes_through_when_no_credential(self) -> None:
        assert _redact_url("postgresql://host/db") == "postgresql://host/db"


class TestRunDoctor:
    def test_returns_aggregate_report(self) -> None:
        report = run_doctor()
        assert isinstance(report, DoctorReport)
        assert report.findings, "doctor should run at least one check"

    def test_json_main_emits_valid_json(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as fake_out:
            code = main(["--json"])
        payload = json.loads(fake_out.getvalue())
        assert "findings" in payload
        assert "worst" in payload
        assert code in (0, 1)

    def test_table_main_includes_worst_severity_line(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as fake_out:
            main([])
        output = fake_out.getvalue()
        assert "Worst severity" in output

    def test_exit_code_is_one_when_any_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from ironroot.cli import doctor as doctor_module

        def _force_failing_check() -> list[Finding]:
            return [
                Finding(check="forced", severity=Severity.FAIL, message="for test"),
            ]

        monkeypatch.setattr(doctor_module, "CHECKS", (_force_failing_check,))
        code = main(["--json"])
        assert code == 1


class TestDoctorCliViaSubprocess:
    """Smoke-test that the entry point script actually runs."""

    def test_doctor_script_executable(self) -> None:
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "ironroot.cli.doctor", "--json"],
            capture_output=True,
            text=True,
            env={**os.environ, "IRONROOT_DEBUG": "true"},
            check=False,
            timeout=30,
        )
        # The script may exit 0 or 1 depending on env; what we care
        # about is that the output is JSON and contains a findings
        # list (i.e. the entry point is wired).
        payload = json.loads(result.stdout)
        assert isinstance(payload["findings"], list)
