# Author: Bradley R. Kinnard
"""Unit tests for ``scripts/check_no_random_in_core.py``.

The build guard must stay correct against three invariants:
1. The integrity-core modules referenced in CLAUDE.md must not contain
   any ``random.*`` or ``numpy.random.*`` reference.
2. The script must accept the same content placed under an experimental
   module prefix.
3. The script must reject the same content under a non-experimental path.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_no_random_in_core.py"


def _run_guard(tmp_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(tmp_path) if tmp_path else None,
    )


class TestGuardOnCurrentTree:
    def test_current_tree_passes(self) -> None:
        result = _run_guard()
        assert (
            result.returncode == 0
        ), f"guard failed on current tree:\nstdout={result.stdout}\nstderr={result.stderr}"


class TestGuardLogic:
    """Synthesize a tiny tree and run the guard against it."""

    def _make_fake_repo(
        self, tmp_path: Path, *, rng_in_experimental: bool, rng_in_core: bool
    ) -> Path:
        src = tmp_path / "src" / "ironroot"
        (src / "experimental").mkdir(parents=True)
        (src / "experimental" / "__init__.py").write_text(textwrap.dedent("""
                EXPERIMENTAL_MODULE_PREFIXES = ("agi",)

                def is_experimental(m: str) -> bool:
                    return any(m == p or m.startswith(p + ".") for p in EXPERIMENTAL_MODULE_PREFIXES)
                """).strip() + "\n")
        (src / "__init__.py").write_text("")

        # Always-clean core module.
        (src / "domain.py").write_text(
            "# Author: test\n" "def hello() -> str:\n" "    return 'no rng here'\n"
        )

        agi = src / "agi"
        agi.mkdir()
        (agi / "__init__.py").write_text("")
        if rng_in_experimental:
            (agi / "tools.py").write_text(
                "import random\n\n" "def pick() -> int:\n" "    return random.randint(0, 9)\n"
            )

        if rng_in_core:
            (src / "verification.py").write_text(
                "import random\n\n" "def gate() -> int:\n" "    return random.randint(0, 9)\n"
            )

        # Drop a copy of the guard script into the fake repo at the
        # expected layout so PYTHONPATH discovery works.
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "check_no_random_in_core.py").write_text(SCRIPT.read_text())
        return tmp_path

    def test_rng_in_experimental_is_allowed(self, tmp_path: Path) -> None:
        repo = self._make_fake_repo(tmp_path, rng_in_experimental=True, rng_in_core=False)
        result = subprocess.run(
            [sys.executable, str(repo / "scripts" / "check_no_random_in_core.py")],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    def test_rng_in_core_is_rejected(self, tmp_path: Path) -> None:
        repo = self._make_fake_repo(tmp_path, rng_in_experimental=False, rng_in_core=True)
        result = subprocess.run(
            [sys.executable, str(repo / "scripts" / "check_no_random_in_core.py")],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "FORBIDDEN RNG REFERENCE" in result.stderr
        assert "verification.py" in result.stderr

    @pytest.mark.parametrize(
        "snippet",
        [
            "import random\n",
            "from random import randint\n",
            "import numpy.random\n",
            "from numpy.random import default_rng\n",
            "x = numpy.random.default_rng()\n",
            "x = np.random.default_rng()\n",
            "import random as rng\n\nrng.random()\nrandom.random()\n",
        ],
    )
    def test_each_pattern_triggers_in_core(self, tmp_path: Path, snippet: str) -> None:
        repo = self._make_fake_repo(tmp_path, rng_in_experimental=False, rng_in_core=False)
        (repo / "src" / "ironroot" / "tainted.py").write_text(snippet)
        result = subprocess.run(
            [sys.executable, str(repo / "scripts" / "check_no_random_in_core.py")],
            capture_output=True,
            text=True,
        )
        assert (
            result.returncode == 1
        ), f"guard accepted {snippet!r} in non-experimental code:\n{result.stdout}\n{result.stderr}"
