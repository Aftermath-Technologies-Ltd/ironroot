# Author: Bradley R. Kinnard
"""Phase 2c.1 — all subsystem callers import BeliefService from the
canonical public path (`ironroot.beliefs`).

The only files allowed to reference the internal
`ironroot.beliefs.belief_service` sub-module by name are:

* `src/ironroot/beliefs/__init__.py` — the public re-export.
* `src/ironroot/cognition/memory/belief_service.py` — the
  deprecation shim that re-exports the canonical class with a
  DeprecationWarning.
* `tests/unit/test_belief_service_consolidation.py` — explicitly
  exercises the deprecation warning.

The legacy `ironroot.cognition.memory.belief_service` path may NOT
appear in any source or test file except its own module and the
consolidation test. The CI test below greps the repo and asserts the
rule. If you need a new import, use `from ironroot.beliefs import …`.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "ironroot"
TEST_ROOT = REPO_ROOT / "tests"

_INTERNAL_IMPORT = re.compile(r"\bfrom\s+ironroot\.beliefs\.belief_service\s+import\b")
_LEGACY_IMPORT = re.compile(r"\bironroot\.cognition\.memory\.belief_service\b")

_ALLOWED_INTERNAL_PATHS: tuple[Path, ...] = (
    SRC_ROOT / "beliefs" / "__init__.py",
    SRC_ROOT / "cognition" / "memory" / "belief_service.py",
    TEST_ROOT / "unit" / "test_belief_service_consolidation.py",
    Path(__file__).resolve(),
)

_ALLOWED_LEGACY_PATHS: tuple[Path, ...] = (
    SRC_ROOT / "cognition" / "memory" / "belief_service.py",
    TEST_ROOT / "unit" / "test_belief_service_consolidation.py",
    Path(__file__).resolve(),
)


def _iter_py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def test_no_caller_imports_from_internal_belief_service_submodule() -> None:
    """`from ironroot.beliefs.belief_service import X` is reserved for the
    public package's __init__ and the deprecation shim.

    Everywhere else uses `from ironroot.beliefs import X`.
    """
    offenders: list[str] = []
    for path in _iter_py_files(SRC_ROOT) + _iter_py_files(TEST_ROOT):
        if path in _ALLOWED_INTERNAL_PATHS:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if _INTERNAL_IMPORT.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        "These files import the internal sub-module path "
        "`ironroot.beliefs.belief_service`. Use `from ironroot.beliefs "
        "import …` instead:\n  - " + "\n  - ".join(offenders)
    )


def test_no_caller_uses_legacy_cognition_memory_belief_service_path() -> None:
    """The legacy `ironroot.cognition.memory.belief_service` path is
    reserved for its own deprecation shim and the consolidation test
    that exercises the shim's DeprecationWarning. No production code
    or other tests should reference it.
    """
    offenders: list[str] = []
    for path in _iter_py_files(SRC_ROOT) + _iter_py_files(TEST_ROOT):
        if path in _ALLOWED_LEGACY_PATHS:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if _LEGACY_IMPORT.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        "These files reference the legacy "
        "`ironroot.cognition.memory.belief_service` path. Use "
        "`from ironroot.beliefs import …` instead:\n  - " + "\n  - ".join(offenders)
    )
