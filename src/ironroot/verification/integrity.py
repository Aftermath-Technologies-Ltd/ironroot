# Author: Bradley R. Kinnard
"""artifact and belief integrity verification."""

from ironroot.cognition.memory.append_only_store import AppendOnlyBeliefStore
from ironroot.storage.artifacts import ArtifactStore


def verify_artifact_integrity(store: ArtifactStore, content_hash: str) -> bool:
    """verifies that stored artifact matches its hash."""
    return store.verify(content_hash)


def verify_belief_chain(belief_store: AppendOnlyBeliefStore) -> bool:
    """verifies the entire belief hash chain."""
    return belief_store.verify_chain()


def verify_all_artifacts(store: ArtifactStore, hashes: list[str]) -> dict[str, bool]:
    """verifies multiple artifacts, returns hash -> pass mapping."""
    return {h: verify_artifact_integrity(store, h) for h in hashes}
