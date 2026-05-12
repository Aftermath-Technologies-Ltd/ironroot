# Author: Bradley R. Kinnard
"""Experimental subsystem manifest.

This package is the single source of truth for which modules in the IRONROOT
codebase are quarantined as **experimental**. Experimental modules are
allowed to be imperfect (RNG-driven, stubbed, partially typed) while the
integrity core (``domain``, ``cognition.memory``, ``storage.artifacts``,
``verification``, ``beliefs``) is held to production grade.

The CI grep guard (``scripts/check_no_random_in_core.py``) reads the
``EXPERIMENTAL_MODULE_PREFIXES`` list below to decide whether a given
``random.``/``numpy.random.`` reference is allowed.

This file deliberately performs **no runtime imports** of the listed
subsystems. Importing this module is cheap and side-effect free.

To move a subsystem out of quarantine ("promote"), satisfy every clause
of the promotion criteria in ``upgrade-plan.md`` Phase 4, remove the
relevant prefix from ``EXPERIMENTAL_MODULE_PREFIXES``, and flip the
matching entry in ``EXPERIMENTAL.md`` from ``experimental`` to
``supported``.
"""

from __future__ import annotations

# Each entry is a dotted module prefix relative to the top-level package
# (i.e. without the leading ``ironroot.``). A module is considered
# experimental if its dotted name starts with any of these prefixes.
EXPERIMENTAL_MODULE_PREFIXES: tuple[str, ...] = (
    "agents",
    "agi",
    "battery",
    "capabilities",
    "cognition.planning",
    "cognition.strategies",
    "evolution",
    "healing",
    "orchestration.executor",
    "reality",
    "research",
    "ui_backend",
    # ``world_models`` graduated to supported at Phase 4 closeout
    # (2026-05-12). See docs/invariants/world_models.md and
    # EXPERIMENTAL.md.
)


def is_experimental(dotted_module: str) -> bool:
    """Return True if ``dotted_module`` is quarantined as experimental.

    ``dotted_module`` is expected without the leading ``ironroot.`` prefix
    (i.e. pass ``"agi.transfer"``, not ``"ironroot.agi.transfer"``).
    """
    return any(
        dotted_module == prefix or dotted_module.startswith(prefix + ".")
        for prefix in EXPERIMENTAL_MODULE_PREFIXES
    )


__all__ = ["EXPERIMENTAL_MODULE_PREFIXES", "is_experimental"]
