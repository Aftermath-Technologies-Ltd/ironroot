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

    def test_public_delete_removed(self) -> None:
        """Phase 1.4: public delete() is no longer part of the API."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(Path(tmpdir))
            assert not hasattr(store, "delete"), (
                "ArtifactStore.delete must be removed to preserve write-once. "
                "Use _unsafe_delete from a retention job if absolutely "
                "necessary."
            )

    def test_unsafe_delete_requires_explicit_consent(self) -> None:
        """_unsafe_delete refuses without the safety kwargs."""
        import pytest

        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(Path(tmpdir))
            content_hash = store.store(b"do not delete me casually")

            # Without the consent kwarg, refuses.
            with pytest.raises(PermissionError):
                store._unsafe_delete(  # type: ignore[call-arg]
                    content_hash, reason="cleanup", operator="ops_bot"
                )

            # With consent but empty reason/operator: refuses.
            with pytest.raises(ValueError):
                store._unsafe_delete(
                    content_hash,
                    reason="",
                    operator="ops_bot",
                    i_understand_this_violates_write_once=True,
                )
            assert store.exists(content_hash)

            # Full required signature succeeds.
            assert store._unsafe_delete(
                content_hash,
                reason="retention-job: orphaned upload, no DB row",
                operator="ops_bot",
                i_understand_this_violates_write_once=True,
            )
            assert not store.exists(content_hash)

    def test_unsafe_delete_logs_tamper_event(self, caplog) -> None:  # type: ignore[no-untyped-def]
        """every _unsafe_delete call emits a WARNING with event=tamper."""
        import logging

        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(Path(tmpdir))
            content_hash = store.store(b"watch this")
            caplog.set_level(logging.WARNING, logger="ironroot.storage.artifacts")
            store._unsafe_delete(
                content_hash,
                reason="orphan cleanup",
                operator="ops_bot",
                i_understand_this_violates_write_once=True,
            )
            tamper_records = [
                r for r in caplog.records if getattr(r, "event", None) == "tamper"
            ]
            assert tamper_records, "expected a tamper-class log entry"
            assert tamper_records[0].levelno == logging.WARNING
            assert getattr(tamper_records[0], "operator", "") == "ops_bot"
