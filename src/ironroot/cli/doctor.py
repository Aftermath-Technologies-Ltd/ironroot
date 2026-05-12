# Author: Bradley R. Kinnard
"""``ironroot doctor`` config auditor (Phase 3.5).

A non-interactive CLI that runs every check an operator would
otherwise have to discover by reading source. Each check produces a
:class:`Finding` with one of:

* ``OK`` — known-good
* ``WARN`` — needs attention but does not block startup (e.g.,
  empty CORS allowlist in production)
* ``FAIL`` — would prevent the service from operating correctly
  (e.g., default DB password in non-debug, alembic head mismatch)

The doctor exits with code 0 on all-pass, 1 if any ``FAIL`` finding
appears. ``WARN`` does not gate the exit code so CI integrations
can treat the script as a build gate without false alarms.

Output is a human-readable table by default; ``--json`` emits the
report as JSON for piping into other tooling.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class Severity(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True)
class Finding:
    """One config check's outcome."""

    check: str
    severity: Severity
    message: str
    recommendation: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class DoctorReport:
    """Aggregate doctor result. Use :meth:`exit_code` to gate CI."""

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

    def exit_code(self) -> int:
        return 1 if self.worst == Severity.FAIL else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "worst": str(self.worst),
            "findings": [asdict(f) for f in self.findings],
        }


def _check_settings() -> list[Finding]:
    """Audits the resolved :class:`ironroot.settings.Settings` block."""
    from ironroot.settings import INSECURE_DEFAULT_PASSWORDS, get_settings

    out: list[Finding] = []
    try:
        settings = get_settings()
    except Exception as exc:  # pragma: no cover - settings is the precondition
        out.append(
            Finding(
                check="settings.load",
                severity=Severity.FAIL,
                message=f"refused to load Settings: {exc}",
                recommendation="export valid IRONROOT_* env vars",
            )
        )
        return out

    out.append(
        Finding(
            check="settings.load",
            severity=Severity.OK,
            message=f"loaded; debug={settings.debug}",
        )
    )

    if settings.db_password in INSECURE_DEFAULT_PASSWORDS and not settings.debug:
        # This branch is normally caught by the Settings validator itself,
        # but we still report it for completeness — and the validator can
        # be bypassed by reaching into the instance directly in tests.
        out.append(
            Finding(
                check="settings.db_password",
                severity=Severity.FAIL,
                message="DB password is one of the known-insecure defaults",
                recommendation="set IRONROOT_DB_PASSWORD to a real value",
            )
        )
    elif settings.db_password in INSECURE_DEFAULT_PASSWORDS:
        out.append(
            Finding(
                check="settings.db_password",
                severity=Severity.WARN,
                message="DB password is a known default; OK because IRONROOT_DEBUG=true",
                recommendation="rotate before IRONROOT_DEBUG=false",
            )
        )
    else:
        out.append(
            Finding(
                check="settings.db_password",
                severity=Severity.OK,
                message="DB password is non-default",
            )
        )

    if not settings.debug and not settings.cors_origins:
        out.append(
            Finding(
                check="settings.cors_origins",
                severity=Severity.WARN,
                message=(
                    "empty allowlist in non-debug mode: "
                    "all cross-origin requests will be denied"
                ),
                recommendation="set IRONROOT_CORS_ORIGINS to a comma-separated list",
            )
        )
    else:
        out.append(
            Finding(
                check="settings.cors_origins",
                severity=Severity.OK,
                message=f"{len(settings.cors_allowed_origins)} origin(s) allowed",
            )
        )

    if settings.auth_required:
        out.append(
            Finding(
                check="settings.auth_required",
                severity=Severity.OK,
                message="API tokens enforced on /api/v1/*",
            )
        )
    else:
        out.append(
            Finding(
                check="settings.auth_required",
                severity=Severity.WARN,
                message="API auth is OFF — anonymous writes are accepted",
                recommendation="set IRONROOT_AUTH_ENABLED=true outside dev",
            )
        )

    if settings.auth_rate_limit_per_minute == 0:
        out.append(
            Finding(
                check="settings.auth_rate_limit_per_minute",
                severity=Severity.WARN,
                message="per-token rate limiting disabled",
                recommendation="set IRONROOT_AUTH_RATE_LIMIT_PER_MINUTE > 0",
            )
        )
    else:
        out.append(
            Finding(
                check="settings.auth_rate_limit_per_minute",
                severity=Severity.OK,
                message=f"{settings.auth_rate_limit_per_minute} req/min/token",
            )
        )

    return out


def _check_artifact_root() -> Finding:
    """Verifies the artifact root is writable.

    Refuses to create the directory if it doesn't exist — the doctor
    is a read-only audit. Creating dirs side-effectfully would mask
    a misconfigured deploy.
    """
    from ironroot.settings import get_settings

    settings = get_settings()
    root: Path = settings.artifact_path
    if not root.exists():
        return Finding(
            check="storage.artifact_path",
            severity=Severity.WARN,
            message=f"{root} does not exist (will be created on first write)",
            recommendation=f"mkdir -p {root}",
        )
    if not root.is_dir():
        return Finding(
            check="storage.artifact_path",
            severity=Severity.FAIL,
            message=f"{root} exists but is not a directory",
            recommendation=f"rm {root} && mkdir {root}",
        )

    probe = root / ".doctor-probe"
    try:
        probe.write_bytes(b"")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        return Finding(
            check="storage.artifact_path",
            severity=Severity.FAIL,
            message=f"{root} is not writable: {exc}",
            recommendation="adjust filesystem permissions",
        )
    return Finding(
        check="storage.artifact_path",
        severity=Severity.OK,
        message=f"{root} writable",
    )


def _check_alembic_head() -> Finding:
    """Compares the codebase's alembic head with the configured DB.

    Best-effort: if the DB is unreachable the check downgrades to
    WARN with the connection error, so a doctor run on a developer
    laptop without Postgres still produces a useful report.
    """
    try:
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory
        from sqlalchemy import create_engine
    except Exception as exc:  # pragma: no cover - alembic always installed
        return Finding(
            check="migrations.alembic_head",
            severity=Severity.WARN,
            message=f"alembic not importable: {exc}",
        )

    # Code-side head.
    cfg_path = Path(__file__).resolve().parent.parent.parent.parent / "alembic.ini"
    if not cfg_path.exists():
        return Finding(
            check="migrations.alembic_head",
            severity=Severity.FAIL,
            message=f"alembic.ini not found at {cfg_path}",
            recommendation="check working directory or repo layout",
        )

    try:
        cfg = Config(str(cfg_path))
        script = ScriptDirectory.from_config(cfg)
        code_head = script.get_current_head()
    except Exception as exc:
        return Finding(
            check="migrations.alembic_head",
            severity=Severity.FAIL,
            message=f"failed to read alembic head from code: {exc}",
        )

    if code_head is None:
        return Finding(
            check="migrations.alembic_head",
            severity=Severity.FAIL,
            message="alembic has no head revision in code",
            recommendation=(
                "add at least one migration under " "src/ironroot/storage/migrations/versions/"
            ),
        )

    from ironroot.settings import get_settings

    db_url = get_settings().sync_database_url
    db_head: str | None = None
    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            db_head = ctx.get_current_revision()
        engine.dispose()
    except Exception as exc:
        return Finding(
            check="migrations.alembic_head",
            severity=Severity.WARN,
            message=f"DB not reachable; cannot compare heads: {exc}",
            details={"code_head": code_head, "db_url": _redact_url(db_url)},
        )

    if db_head is None:
        return Finding(
            check="migrations.alembic_head",
            severity=Severity.FAIL,
            message="DB has no alembic version row",
            recommendation="run `alembic upgrade head` against the configured DB",
            details={"code_head": code_head},
        )
    if db_head != code_head:
        return Finding(
            check="migrations.alembic_head",
            severity=Severity.FAIL,
            message=f"DB at {db_head}, code at {code_head}",
            recommendation="run `alembic upgrade head` against the configured DB",
            details={"code_head": code_head, "db_head": db_head},
        )
    return Finding(
        check="migrations.alembic_head",
        severity=Severity.OK,
        message=f"DB and code both at {code_head}",
        details={"code_head": code_head, "db_head": db_head},
    )


def _redact_url(url: str) -> str:
    """Drops the password from a DSN-style URL for logging."""
    if "@" not in url or ":" not in url:
        return url
    scheme_split = url.split("://", 1)
    if len(scheme_split) != 2:
        return url
    scheme, rest = scheme_split
    cred, host = rest.split("@", 1)
    if ":" in cred:
        user, _ = cred.split(":", 1)
        cred = f"{user}:***"
    return f"{scheme}://{cred}@{host}"


def _check_redis() -> Finding:
    """Best-effort PING against the configured Redis broker."""
    try:
        from redis import Redis
    except Exception as exc:  # pragma: no cover - redis is a hard dep
        return Finding(
            check="redis.ping",
            severity=Severity.WARN,
            message=f"redis client not installed: {exc}",
        )

    from ironroot.settings import get_settings

    settings = get_settings()
    try:
        client: Any = Redis.from_url(settings.redis_url, socket_timeout=2)
        ok = client.ping()
        client.close()
    except Exception as exc:
        return Finding(
            check="redis.ping",
            severity=Severity.WARN,
            message=f"redis ping failed: {exc}",
            recommendation="start redis or fix IRONROOT_REDIS_* settings",
        )
    return Finding(
        check="redis.ping",
        severity=Severity.OK if ok else Severity.WARN,
        message="PONG" if ok else "ping returned falsy",
    )


def _check_rng_guard() -> Finding:
    """Runs the codebase's own no-random-in-core guard.

    The CI invokes ``scripts/check_no_random_in_core.py`` already.
    Running it from the doctor keeps a single command operators can
    run locally to catch a regression before pushing.
    """
    import subprocess

    script = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "scripts"
        / "check_no_random_in_core.py"
    )
    if not script.exists():
        return Finding(
            check="guards.no_random_in_core",
            severity=Severity.WARN,
            message=f"guard script missing at {script}",
        )
    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, check=False
    )
    if result.returncode == 0:
        return Finding(
            check="guards.no_random_in_core",
            severity=Severity.OK,
            message="no random.* imports outside experimental.* / tests/",
        )
    return Finding(
        check="guards.no_random_in_core",
        severity=Severity.FAIL,
        message=result.stdout.strip() or result.stderr.strip() or "guard failed",
        recommendation="move RNG code under ironroot.experimental.* or delete it",
    )


CHECKS = (
    _check_settings,
    lambda: [_check_artifact_root()],
    lambda: [_check_alembic_head()],
    lambda: [_check_redis()],
    lambda: [_check_rng_guard()],
)


def run_doctor() -> DoctorReport:
    """Runs every registered check and returns the aggregate report."""
    report = DoctorReport()
    for check in CHECKS:
        for finding in check():
            report.add(finding)
    return report


def _render_table(report: DoctorReport) -> str:
    rows = []
    for f in report.findings:
        rec = f" → {f.recommendation}" if f.recommendation else ""
        rows.append(f"[{f.severity.upper():<4}] {f.check:<35} {f.message}{rec}")
    rows.append("")
    rows.append(f"Worst severity: {report.worst.upper()}")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ironroot-doctor",
        description="Audit IRONROOT config and dependencies.",
    )
    parser.add_argument(
        "--json", action="store_true", help="emit the report as JSON instead of a table"
    )
    args = parser.parse_args(argv)

    report = run_doctor()

    if args.json:
        sys.stdout.write(json.dumps(report.to_dict(), indent=2, default=str) + "\n")
    else:
        sys.stdout.write(_render_table(report) + "\n")

    return report.exit_code()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
