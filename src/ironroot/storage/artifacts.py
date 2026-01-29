# Author: Bradley R. Kinnard
"""content-addressed artifact storage with write-once semantics."""

import shutil
from pathlib import Path

from ironroot.domain.errors import IntegrityError, NotFoundError
from ironroot.domain.ids import hash_content, verify_hash
from ironroot.settings import get_settings


class ArtifactStore:
    """local filesystem artifact store with sha256 content addressing."""

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

    def delete(self, content_hash: str) -> bool:
        """deletes artifact, returns true if existed."""
        artifact_path = self._get_artifact_path(content_hash)
        if artifact_path.exists():
            shutil.rmtree(artifact_path.parent)
            return True
        return False
