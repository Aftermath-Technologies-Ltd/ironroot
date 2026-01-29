# Author: Bradley R. Kinnard
"""unit tests for integrity hashing and verification."""

import tempfile
from pathlib import Path

import pytest

from ironroot.domain.errors import IntegrityError, NotFoundError
from ironroot.storage.artifacts import ArtifactStore


class TestArtifactStoreIntegrity:
    """tests for artifact store integrity."""

    def test_store_and_retrieve(self) -> None:
        """storing and retrieving preserves content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(Path(tmpdir))
            data = b"test artifact content"

            content_hash = store.store(data)
            retrieved = store.retrieve(content_hash)

            assert retrieved == data

    def test_same_content_same_hash(self) -> None:
        """storing same content returns same hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(Path(tmpdir))
            data = b"identical content"

            hash1 = store.store(data)
            hash2 = store.store(data)

            assert hash1 == hash2

    def test_different_content_different_hash(self) -> None:
        """different content produces different hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(Path(tmpdir))

            hash1 = store.store(b"content a")
            hash2 = store.store(b"content b")

            assert hash1 != hash2

    def test_retrieve_nonexistent_raises(self) -> None:
        """retrieving nonexistent artifact raises NotFoundError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(Path(tmpdir))

            with pytest.raises(NotFoundError):
                store.retrieve("nonexistent_hash")

    def test_verify_correct(self) -> None:
        """verification passes for stored artifact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(Path(tmpdir))
            content_hash = store.store(b"test data")

            assert store.verify(content_hash)

    def test_verify_nonexistent(self) -> None:
        """verification fails for nonexistent artifact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(Path(tmpdir))

            assert not store.verify("nonexistent_hash")

    def test_tamper_detection(self) -> None:
        """tampered artifact fails integrity check."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(Path(tmpdir))
            original = b"original content"
            content_hash = store.store(original)

            # tamper with the stored file
            artifact_path = store._get_artifact_path(content_hash)
            artifact_path.write_bytes(b"tampered content")

            # verification should fail
            assert not store.verify(content_hash)

            # retrieval should raise
            with pytest.raises(IntegrityError):
                store.retrieve(content_hash)

    def test_exists(self) -> None:
        """exists returns correct status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(Path(tmpdir))

            assert not store.exists("nonexistent")

            content_hash = store.store(b"test")
            assert store.exists(content_hash)

    def test_delete(self) -> None:
        """delete removes artifact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(Path(tmpdir))
            content_hash = store.store(b"to delete")

            assert store.exists(content_hash)
            assert store.delete(content_hash)
            assert not store.exists(content_hash)

    def test_delete_nonexistent(self) -> None:
        """delete returns false for nonexistent artifact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(Path(tmpdir))

            assert not store.delete("nonexistent")
