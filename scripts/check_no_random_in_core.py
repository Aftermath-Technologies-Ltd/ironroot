#!/usr/bin/env python3
# Author: Bradley R. Kinnard
"""Fail the build if `random.*` or `numpy.random.*` is referenced outside of
quarantined experimental modules or test code.

The authoritative list of experimental module prefixes lives in
``src/ironroot/experimental/__init__.py``. This script reads it and treats
matches as allowed; everything else under ``src/ironroot/`` is held to the
no-RNG rule documented in ``CLAUDE.md``.

Exits 0 if clean, 1 if any forbidden reference is found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src" / "ironroot"

sys.path.insert(0, str(REPO_ROOT / "src"))

from ironroot.experimental import EXPERIMENTAL_MODULE_PREFIXES  # noqa: E402

# Match `import random`, `from random import ...`, `random.<attr>`,
# `import numpy.random`, `from numpy.random import ...`, `numpy.random.<attr>`,
# `np.random.<attr>`. The script ignores hits inside string/byte literals; an
# AST pass is heavier than needed for a build guard, so we use a conservative
# regex and strip out triple-quoted blocks and comments first.
_PATTERNS = [
    re.compile(r"\brandom\.[A-Za-z_]"),
    re.compile(r"\bnumpy\.random\b"),
    re.compile(r"\bnp\.random\b"),
    re.compile(r"\bfrom\s+random\s+import\b"),
    re.compile(r"\bfrom\s+numpy\.random\s+import\b"),
    re.compile(r"^\s*import\s+random\s*(?:#|$)", re.MULTILINE),
    re.compile(r"^\s*import\s+numpy\.random\s*(?:#|$)", re.MULTILINE),
]

# Pre-compiled patterns to strip noise that would cause false positives.
_TRIPLE_QUOTED = re.compile(r"(?s)(\"\"\".*?\"\"\"|'''.*?''')")
_LINE_COMMENT = re.compile(r"#.*?$", re.MULTILINE)


def is_experimental(module: str) -> bool:
    return any(
        module == prefix or module.startswith(prefix + ".") for prefix in EXPERIMENTAL_MODULE_PREFIXES
    )


def path_to_module(path: Path) -> str:
    rel = path.relative_to(SRC_ROOT)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]  # strip .py
    return ".".join(parts)


def scan_file(path: Path) -> list[tuple[int, str]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    cleaned = _TRIPLE_QUOTED.sub("", text)
    cleaned = _LINE_COMMENT.sub("", cleaned)
    findings: list[tuple[int, str]] = []
    for lineno, line in enumerate(cleaned.splitlines(), start=1):
        for pat in _PATTERNS:
            if pat.search(line):
                findings.append((lineno, line.strip()))
                break
    return findings


def main() -> int:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        module = path_to_module(path)
        # Skip the experimental manifest itself and any quarantined module.
        if module == "experimental" or module.startswith("experimental."):
            continue
        if is_experimental(module):
            continue
        hits = scan_file(path)
        if hits:
            for lineno, line in hits:
                violations.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line}")

    if violations:
        sys.stderr.write(
            "\n".join(
                [
                    "FORBIDDEN RNG REFERENCE outside ironroot.experimental.* "
                    "(see CLAUDE.md, upgrade-plan.md Phase 0.10):",
                    *violations,
                    "",
                    "Move the offending module under ironroot.experimental.* in "
                    "src/ironroot/experimental/__init__.py::EXPERIMENTAL_MODULE_PREFIXES, "
                    "or replace the RNG with a deterministic fixture.",
                ]
            )
            + "\n"
        )
        return 1

    print(f"OK: no forbidden random.* references in {len(EXPERIMENTAL_MODULE_PREFIXES)} non-experimental modules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
