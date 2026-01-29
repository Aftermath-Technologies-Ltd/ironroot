# Author: Bradley R. Kinnard
"""replay determinism verification."""

from dataclasses import dataclass

from ironroot.domain.ids import hash_content


@dataclass
class ReplayDigest:
    """digest of a run for determinism checking."""

    run_id: str
    seed: int
    trace_hash: str
    artifact_hashes: tuple[str, ...]
    belief_chain_hash: str


def compute_trace_digest(events: list[bytes]) -> str:
    """computes hash of all trace events in order."""
    combined = b"".join(events)
    return hash_content(combined)


def compute_replay_digest(
    run_id: str,
    seed: int,
    trace_events: list[bytes],
    artifact_hashes: list[str],
    belief_chain_hash: str,
) -> ReplayDigest:
    """computes full replay digest for a run."""
    trace_hash = compute_trace_digest(trace_events)

    return ReplayDigest(
        run_id=run_id,
        seed=seed,
        trace_hash=trace_hash,
        artifact_hashes=tuple(sorted(artifact_hashes)),
        belief_chain_hash=belief_chain_hash,
    )


def verify_replay(original: ReplayDigest, replayed: ReplayDigest) -> bool:
    """verifies that a replay matches the original run."""
    if original.seed != replayed.seed:
        return False
    if original.trace_hash != replayed.trace_hash:
        return False
    if original.artifact_hashes != replayed.artifact_hashes:
        return False
    return original.belief_chain_hash == replayed.belief_chain_hash
