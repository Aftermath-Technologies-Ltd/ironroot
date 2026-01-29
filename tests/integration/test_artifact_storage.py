# Author: Bradley R. Kinnard
"""integration tests for artifact storage."""

import tempfile
from pathlib import Path

from ironroot.storage.artifacts import ArtifactStore


class TestArtifactStorage:
    """integration tests for artifact store."""

    def test_full_lifecycle(self) -> None:
        """store, retrieve, verify, delete lifecycle."""
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

            # delete
            assert store.delete(content_hash)
            assert not store.exists(content_hash)

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
