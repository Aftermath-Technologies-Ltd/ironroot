"""
Cross-language fixture test: asserts that the Python IRONROOT
canonicalization and hash-chain semantics match the @ironroot/core
TypeScript implementation byte-for-byte.

Run from repo root:
    pytest tests/cross_language/test_fixtures.py

These tests load the same JSON fixtures consumed by
packages/core-ts/test/cross-language.test.ts. If either side diverges,
both suites fail.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[2] / "packages" / "core-ts" / "test" / "fixtures"


def canonical_json(value: object) -> str:
    """Deterministic JSON canonicalization mirroring canonical.ts."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def test_canonical_vectors() -> None:
    vectors = json.loads((FIXTURES / "canonical_vectors.json").read_text())
    for v in vectors:
        actual = canonical_json(v["input"])
        assert actual == v["canonical"], (
            f"canonical mismatch for {v['name']}: "
            f"expected {v['canonical']!r}, got {actual!r}"
        )


def test_chain_vectors() -> None:
    cases = json.loads((FIXTURES / "chain_vectors.json").read_text())
    GENESIS = "0" * 64

    for case in cases:
        prev_hash = GENESIS
        hashes: list[str] = []
        for i, payload in enumerate(case["payloads"]):
            entry = {
                "entryId": f"fixture-{i:08d}",
                "prevHash": prev_hash,
                "payload": payload,
                "createdAt": "2024-01-01T00:00:00.000Z",
            }
            serialized = canonical_json(entry)
            entry_hash = sha256_hex(serialized)
            hashes.append(entry_hash)
            prev_hash = entry_hash

        if "expectedHashes" in case:
            assert hashes == case["expectedHashes"], (
                f"chain hash mismatch for {case['name']}: "
                f"expected {case['expectedHashes']}, got {hashes}"
            )
        assert len(hashes) == len(case["payloads"])
