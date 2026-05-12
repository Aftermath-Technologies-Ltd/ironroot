# Author: Bradley R. Kinnard
"""content-addressed artifact storage with write-once semantics.

Phase 1.4 (Phase 1) made the store genuinely write-once: the public API
exposes ``store``, ``retrieve``, ``exists``, ``verify``. The old
``delete()`` method was removed. Operationally a retention job may need
to garbage-collect orphaned uploads — for that case there is
``_unsafe_delete``, which is intentionally underscored, refuses to run
unless explicitly opted in, and logs every invocation at WARNING level
as a tamper-class event so an operator can audit any deletion.
"""

import logging
import shutil
from pathlib import Path

from ironroot.domain.errors import IntegrityError, NotFoundError
from ironroot.domain.ids import hash_content, verify_hash
from ironroot.settings import get_settings

logger = logging.getLogger(__name__)


class ArtifactStore:
    """local filesystem artifact store with sha256 content addressing.

    Write-once: once an artifact is stored at ``content_hash``, subsequent
    ``store()`` calls with the same content are idempotent and verify the
    existing bytes match. There is no public mutation or delete path.
    """

    def __init__(self, base_path: Path | None = None) -> None:
        settings = get_settings()
        self.base_path = base_path or settings.artifact_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_artifact_path(self, content_hash: str) -> Path:
        """returns path: base/prefix/hash/content."""
        prefix = content_hash[:4]
        return self.base_path / prefix / content_hash / "content"

    def store(self, data: bytes, artifact_type: str = "blob") -> str:
        """stores bytes and returns content hash, enforces write-once."""
        content_hash = hash_content(data)
        artifact_path = self._get_artifact_path(content_hash)

        if artifact_path.exists():
            # write-once: verify existing content matches
            existing = artifact_path.read_bytes()
            if not verify_hash(existing, content_hash):
                raise IntegrityError(f"existing artifact corrupted: {content_hash}")
            return content_hash

        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(data)

        # write metadata
        meta_path = artifact_path.parent / "meta.txt"
        meta_path.write_text(f"type={artifact_type}\nhash={content_hash}\n")

        return content_hash

    def retrieve(self, content_hash: str) -> bytes:
        """retrieves bytes by hash, verifies integrity."""
        artifact_path = self._get_artifact_path(content_hash)

        if not artifact_path.exists():
            raise NotFoundError("artifact", content_hash)

        data = artifact_path.read_bytes()

        if not verify_hash(data, content_hash):
            raise IntegrityError(f"artifact integrity check failed: {content_hash}")

        return data

    def exists(self, content_hash: str) -> bool:
        """checks if artifact exists."""
        return self._get_artifact_path(content_hash).exists()

    def verify(self, content_hash: str) -> bool:
        """verifies artifact integrity without returning data."""
        try:
            artifact_path = self._get_artifact_path(content_hash)
            if not artifact_path.exists():
                return False
            data = artifact_path.read_bytes()
            return verify_hash(data, content_hash)
        except Exception:
            return False

    def _unsafe_delete(
        self,
        content_hash: str,
        *,
        reason: str,
        operator: str,
        i_understand_this_violates_write_once: bool = False,
    ) -> bool:
        """retention-only escape hatch — NOT part of the public API.

        Required for genuinely-orphaned uploads where no DB row references
        the bytes on disk. Refuses to run without the explicit consent
        kwarg, requires a reason and operator id, and logs every call at
        WARNING with the tag ``tamper`` so audits can surface every
        deletion. Callers must justify why this is not a chain violation
        in the ``reason`` field.

        Returns True if a file was actually removed, False if it did not
        exist. Raises ``PermissionError`` if the safety kwarg is missing
        so a stray ``store._unsafe_delete(h)`` call cannot silently
        succeed.
        """
        if not i_understand_this_violates_write_once:
            raise PermissionError(
                "_unsafe_delete refused: pass "
                "i_understand_this_violates_write_once=True and supply "
                "reason= and operator= to confirm an intentional delete."
            )
        if not reason or not operator:
            raise ValueError("_unsafe_delete refused: reason= and operator= must be non-empty")

        artifact_path = self._get_artifact_path(content_hash)
        existed = artifact_path.exists()
        logger.warning(
            "tamper-class event: ArtifactStore._unsafe_delete called",
            extra={
                "event": "tamper",
                "action": "_unsafe_delete",
                "content_hash": content_hash,
                "existed": existed,
                "reason": reason,
                "operator": operator,
            },
        )
        if existed:
            shutil.rmtree(artifact_path.parent)
            return True
        return False
