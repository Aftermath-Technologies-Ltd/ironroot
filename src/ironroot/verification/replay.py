# Author: Bradley R. Kinnard
"""Replay determinism via stored chain digest (Phase 1.5).

The replay gate's job is to detect non-determinism: a chain that
produces different rows on re-execution. The mechanism:

1. **Compute** a canonical digest of the chain rows in `seq` order. Each
   row contributes ``(seq, parent_hash_or_empty, content_hash,
   agent_id, belief_type)`` joined with a NUL byte; rows are joined with
   newlines; the whole thing is sha256'd.
2. **Seal** the digest on the `RunRecord` at run completion. Sealing is
   idempotent — the first seal wins; subsequent seal attempts on a
   mismatched chain are reported back as a determinism violation.
3. **Compare** on every replay-gate run: recompute the live digest,
   match against the sealed baseline. Mismatch -> gate fails with the
   typed reason in the gate's evidence.

Any in-place mutation of a belief row (`content`, `agent_id`,
`belief_type`, etc. — anything that's part of `content_hash`) changes
the digest. Reordering, dropping, or inserting rows also changes the
digest because `seq` is part of the per-row payload. Tampering is
caught.

The old behaviour — "_check_replay re-runs verify_chain" — has been
deleted. That check passed whenever the live chain was internally
consistent, which is what the integrity gate already verifies. The
replay gate now does something distinct: compare to a stored baseline.

The legacy ``ReplayDigest`` / ``compute_replay_digest`` API surface is
preserved for the cross-language `@ironroot/core` parity fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import select

from ironroot.domain.ids import hash_content
from ironroot.storage.models import BeliefRecord

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class _BeliefDigestRow(Protocol):
    """structural subset of a BeliefRecord used for digest computation."""

    seq: int
    parent_hash: str | None
    content_hash: str
    agent_id: str
    belief_type: str


_ROW_FIELD_SEP = b"\x00"
_ROW_SEP = b"\n"


def compute_chain_digest_from_rows(rows: list[_BeliefDigestRow]) -> str:
    """canonical sha256 of a chain, ordered by seq.

    The input MUST already be in seq order. Rows with a non-monotonic
    seq are rejected; callers should fix the chain before calling. We
    don't sort here on purpose: the gate must surface ordering
    anomalies, not silently paper over them.
    """
    parts: list[bytes] = []
    expected = 1
    for row in rows:
        if row.seq != expected:
            raise ValueError(
                f"chain rows out of order: expected seq={expected}, got "
                f"seq={row.seq}. Fix the chain or use the integrity gate "
                "first."
            )
        expected += 1
        parts.append(
            _ROW_FIELD_SEP.join(
                [
                    str(row.seq).encode(),
                    (row.parent_hash or "").encode(),
                    row.content_hash.encode(),
                    row.agent_id.encode(),
                    row.belief_type.encode(),
                ]
            )
        )
    return hash_content(_ROW_SEP.join(parts))


async def compute_chain_digest(session: AsyncSession, run_id: str) -> str:
    """fetches the chain in seq order and returns its canonical digest.

    Returns the empty-chain sentinel (sha256 of empty bytes) when the
    chain has no rows. Callers that want to distinguish empty from
    non-empty can check the chain length separately; the digest itself
    is well-defined for both cases.
    """
    result = await session.execute(
        select(BeliefRecord).where(BeliefRecord.run_id == run_id).order_by(BeliefRecord.seq.asc())
    )
    rows = list(result.scalars().all())
    return compute_chain_digest_from_rows(rows)  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# Legacy parity API (preserved for @ironroot/core cross-language tests).
# Don't add new callers — use compute_chain_digest above.
# ----------------------------------------------------------------------


@dataclass
class ReplayDigest:
    """digest of a run for determinism checking (legacy parity API)."""

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
    """computes full replay digest for a run (legacy parity API)."""
    trace_hash = compute_trace_digest(trace_events)
    return ReplayDigest(
        run_id=run_id,
        seed=seed,
        trace_hash=trace_hash,
        artifact_hashes=tuple(sorted(artifact_hashes)),
        belief_chain_hash=belief_chain_hash,
    )


def verify_replay(original: ReplayDigest, replayed: ReplayDigest) -> bool:
    """verifies that a replay matches the original run (legacy parity API)."""
    if original.seed != replayed.seed:
        return False
    if original.trace_hash != replayed.trace_hash:
        return False
    if original.artifact_hashes != replayed.artifact_hashes:
        return False
    return original.belief_chain_hash == replayed.belief_chain_hash
