# Author: Bradley R. Kinnard
"""IRONROOT command-line interface package.

Currently ships two subcommands behind ``python -m ironroot.cli``:

* ``ironroot serve``  — the existing uvicorn launcher
  (also reachable as the project script ``ironroot``).
* ``ironroot doctor`` — Phase 3.5 config auditor. Prints a
  structured report of every settings/permission/dependency
  finding and exits non-zero if any check is at FAIL severity.
"""

from ironroot.cli.doctor import DoctorReport, Finding, Severity, run_doctor

__all__ = ["DoctorReport", "Finding", "Severity", "run_doctor"]
