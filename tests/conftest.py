# Author: Bradley R. Kinnard
"""pytest configuration and fixtures.

Environment defaults set here must run BEFORE ``ironroot.settings`` is
imported anywhere, otherwise the ``Settings`` validator will reject the
shipped default password. Setting ``IRONROOT_DEBUG=true`` keeps the local
test suite in dev mode by default; tests that exercise production-mode
behaviour explicitly construct ``Settings(debug=False, ...)``.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

# Force test runs into debug mode so the password guard added in
# Phase 0.9 doesn't refuse to start under the default `changeme`. Real
# deployments are expected to set a real password and IRONROOT_DEBUG=false.
os.environ.setdefault("IRONROOT_DEBUG", "true")

import pytest  # noqa: E402

from ironroot.storage.artifacts import ArtifactStore  # noqa: E402


@pytest.fixture
def temp_artifact_store() -> Generator[ArtifactStore, None, None]:
    """provides a temporary artifact store for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield ArtifactStore(Path(tmpdir))
