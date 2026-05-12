# Author: Bradley R. Kinnard
"""integration tests for artifact storage."""

import tempfile
from pathlib import Path

import pytest

from ironroot.domain.errors import IntegrityError
from ironroot.storage.artifacts import ArtifactStore


class TestArtifactStorage:
    """integration tests for artifact store."""

    def test_full_lifecycle(self) -> None:
        """store, retrieve, verify lifecycle (no public delete after Phase 1.4)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(Path(tmpdir))

            # store
            data = b"test artifact data for lifecycle"
            content_hash = store.store(data, artifact_type="test")

            # exists
            assert store.exists(content_hash)

            # retrieve
            retrieved = store.retrieve(content_hash)
            assert retrieved == data

            # verify
            assert store.verify(content_hash)

            # Public delete is gone (Phase 1.4: write-once enforcement).
            assert not hasattr(store, "delete")

    def test_write_once_semantics(self) -> None:
        """writing same content twice is idempotent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(Path(tmpdir))

            data = b"idempotent content"

            hash1 = store.store(data)
            hash2 = store.store(data)

            assert hash1 == hash2

            # should still be retrievable
            assert store.retrieve(hash1) == data

    def test_multiple_artifacts(self) -> None:
        """can store and retrieve multiple artifacts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(Path(tmpdir))

            hashes = []
            for i in range(10):
                data = f"artifact {i}".encode()
                h = store.store(data)
                hashes.append((h, data))

            # all retrievable
            for h, expected in hashes:
                assert store.retrieve(h) == expected

    def test_large_artifact(self) -> None:
        """can handle larger artifacts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(Path(tmpdir))

            # 1MB artifact
            data = b"x" * (1024 * 1024)
            content_hash = store.store(data)

            retrieved = store.retrieve(content_hash)
            assert retrieved == data
            assert store.verify(content_hash)

    def test_tamper_detection_raises_on_retrieve(self) -> None:
        """tampered artifact raises IntegrityError on retrieval."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(Path(tmpdir))

            original = b"original untampered content"
            content_hash = store.store(original)

            # tamper with stored bytes
            artifact_path = store._get_artifact_path(content_hash)
            artifact_path.write_bytes(b"maliciously modified content")

            # retrieve must detect and raise
            with pytest.raises(IntegrityError) as exc_info:
                store.retrieve(content_hash)

            assert content_hash in str(exc_info.value)

    def test_tamper_detection_verify_returns_false(self) -> None:
        """verify returns false for tampered artifact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(Path(tmpdir))

            original = b"content before tampering"
            content_hash = store.store(original)

            # confirm initially valid
            assert store.verify(content_hash) is True

            # tamper
            artifact_path = store._get_artifact_path(content_hash)
            artifact_path.write_bytes(b"different bytes")

            # verify now returns false
            assert store.verify(content_hash) is False

    def test_hash_equality_across_stores(self) -> None:
        """same content produces same hash in different stores."""
        data = b"content for cross-store hash test"

        with (
            tempfile.TemporaryDirectory() as tmpdir1,
            tempfile.TemporaryDirectory() as tmpdir2,
        ):
            store1 = ArtifactStore(Path(tmpdir1))
            store2 = ArtifactStore(Path(tmpdir2))

            hash1 = store1.store(data)
            hash2 = store2.store(data)

            assert hash1 == hash2

    def test_content_addressing_is_deterministic(self) -> None:
        """content addressing produces reproducible hashes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(Path(tmpdir))

            # store same content multiple times
            content = b"deterministic hash content"
            hashes = [store.store(content) for _ in range(5)]

            # all hashes must be identical
            assert len(set(hashes)) == 1
