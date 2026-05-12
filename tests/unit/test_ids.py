# Author: Bradley R. Kinnard
"""unit tests for id generation and hashing."""

from __future__ import annotations

import re
import typing
from pathlib import Path

import pytest

from ironroot.domain.ids import IdPrefix, generate_id, hash_content, verify_hash

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCAN_DIRS = (_REPO_ROOT / "src" / "ironroot", _REPO_ROOT / "tests")
_CALL_RE = re.compile(r"""generate_id\(\s*["']([a-z][a-z0-9_]*)["']\s*\)""")


def _declared_prefixes() -> set[str]:
    return set(typing.get_args(IdPrefix))


def _call_site_prefixes() -> set[str]:
    found: set[str] = set()
    for root in _SCAN_DIRS:
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for match in _CALL_RE.finditer(text):
                found.add(match.group(1))
    return found


class TestGenerateId:
    """tests for id generation."""

    def test_generates_prefixed_id(self) -> None:
        """id has correct prefix."""
        run_id = generate_id("run")
        assert run_id.startswith("run_")

    def test_ids_are_unique(self) -> None:
        """consecutive ids are different."""
        ids = [generate_id("run") for _ in range(100)]
        assert len(set(ids)) == 100

    def test_all_prefixes_work(self) -> None:
        """all valid prefixes produce valid ids."""
        prefixes = ["run", "bel", "art", "str", "inc", "gat"]
        for prefix in prefixes:
            result = generate_id(prefix)  # type: ignore[arg-type]
            assert result.startswith(f"{prefix}_")

    def test_invalid_prefix_rejected_at_runtime(self) -> None:
        """generate_id raises on prefixes that don't match the format."""
        with pytest.raises(ValueError):
            generate_id("UPPER")  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            generate_id("")  # type: ignore[arg-type]


class TestPrefixDeclarations:
    """asserts every prefix used in the repo is declared in the Literal."""

    def test_every_call_site_prefix_is_declared(self) -> None:
        declared = _declared_prefixes()
        used = _call_site_prefixes()
        undeclared = used - declared
        assert not undeclared, (
            f"these prefixes are passed to generate_id() but not declared "
            f"in IdPrefix: {sorted(undeclared)}. Add them to "
            f"src/ironroot/domain/ids.py::IdPrefix."
        )

    def test_no_orphan_declared_prefixes(self) -> None:
        """declared prefixes that are nowhere called should be removed."""
        declared = _declared_prefixes()
        used = _call_site_prefixes()
        orphans = declared - used
        assert not orphans, (
            f"these prefixes are declared in IdPrefix but never used; "
            f"remove them: {sorted(orphans)}"
        )


class TestHashing:
    """tests for content hashing."""

    def test_same_content_same_hash(self) -> None:
        """identical content produces identical hash."""
        data = b"test content"
        hash1 = hash_content(data)
        hash2 = hash_content(data)
        assert hash1 == hash2

    def test_different_content_different_hash(self) -> None:
        """different content produces different hash."""
        hash1 = hash_content(b"content a")
        hash2 = hash_content(b"content b")
        assert hash1 != hash2

    def test_verify_hash_correct(self) -> None:
        """verification passes for correct hash."""
        data = b"test data"
        content_hash = hash_content(data)
        assert verify_hash(data, content_hash)

    def test_verify_hash_incorrect(self) -> None:
        """verification fails for wrong hash."""
        data = b"test data"
        wrong_hash = hash_content(b"other data")
        assert not verify_hash(data, wrong_hash)

    def test_hash_is_hex_string(self) -> None:
        """hash is a valid hex string."""
        result = hash_content(b"test")
        assert all(c in "0123456789abcdef" for c in result)
        assert len(result) == 64  # sha256 produces 64 hex chars
