# Author: Bradley R. Kinnard
"""pytest configuration and fixtures."""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from ironroot.storage.artifacts import ArtifactStore


@pytest.fixture
def temp_artifact_store() -> Generator[ArtifactStore, None, None]:
    """provides a temporary artifact store for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield ArtifactStore(Path(tmpdir))
