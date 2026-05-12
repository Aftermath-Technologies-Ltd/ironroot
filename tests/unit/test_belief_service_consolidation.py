# Author: Bradley R. Kinnard
"""Phase 1.7 — only one BeliefService class exists in src/ironroot.

The canonical implementation lives at
``src/ironroot/beliefs/belief_service.py``. The legacy module at
``src/ironroot/cognition/memory/belief_service.py`` is a
DeprecationWarning shim and must not redefine the class.

The test greps for ``class BeliefService`` over all source files. If a
new implementation is reintroduced, this test fails fast.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CLASS_DEF_RE = re.compile(r"^\s*class\s+BeliefService\b", re.MULTILINE)
SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "ironroot"


def test_only_one_belief_service_class_in_source() -> None:
    """exactly one ``class BeliefService`` definition under src/ironroot."""
    matches: list[tuple[Path, int]] = []
    for py in SRC_ROOT.rglob("*.py"):
        text = py.read_text()
        for m in CLASS_DEF_RE.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            matches.append((py, line))

    assert len(matches) == 1, (
        "Expected exactly one `class BeliefService` definition in "
        f"src/ironroot/, found {len(matches)}: {matches}. The canonical "
        "service is in ironroot.beliefs.belief_service; reintroducing "
        "a parallel class is a Phase 1.7 violation."
    )

    canonical, _line = matches[0]
    rel = canonical.relative_to(SRC_ROOT.parent.parent)
    assert rel.as_posix() == "src/ironroot/beliefs/belief_service.py", (
        f"BeliefService is defined in {rel} but the canonical home is "
        "src/ironroot/beliefs/belief_service.py."
    )


def test_legacy_shim_re_exports_canonical_class() -> None:
    """the deprecated module exports the SAME class object, not a clone."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)

        from ironroot.beliefs import BeliefService as canonical
        from ironroot.cognition.memory.belief_service import (
            BeliefService as shimmed,
        )
    assert canonical is shimmed


def test_legacy_shim_emits_deprecation_warning() -> None:
    """importing the legacy module triggers DeprecationWarning."""
    import importlib
    import sys
    import warnings

    # If already imported the warning has already fired; force a fresh import.
    sys.modules.pop("ironroot.cognition.memory.belief_service", None)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always", DeprecationWarning)
        importlib.import_module("ironroot.cognition.memory.belief_service")
    deprecations = [
        rec
        for rec in w
        if issubclass(rec.category, DeprecationWarning) and "belief_service" in str(rec.message)
    ]
    assert deprecations, "expected DeprecationWarning from the legacy shim"


@pytest.mark.parametrize(
    "name",
    [
        "BeliefService",
        "BeliefType",
        "MetricClass",
        "PredictionStatus",
        "PRIMARY_METRIC_NAMES",
        "VERIFIER_ARTIFACT_TYPES",
        "get_belief_service",
        "ContradictionService",
        "get_contradiction_service",
    ],
)
def test_canonical_surface_exports(name: str) -> None:
    """the canonical package exposes the full public surface."""
    from ironroot import beliefs

    assert hasattr(beliefs, name), f"ironroot.beliefs is missing {name!r}"
