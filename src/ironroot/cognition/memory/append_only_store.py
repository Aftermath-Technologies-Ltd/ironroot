# Author: Bradley R. Kinnard
"""In-memory append-only belief store — reference implementation.

This module is the **canonical reference** for the chain-hash algorithm.
It exists for three reasons (Phase 1.8 decision):

1. It is the cross-language parity target. The TypeScript port
   ``@ironroot/core`` ships ``AppendOnlyBeliefStore`` with identical
   semantics, and the fixtures under ``packages/core-ts/test/fixtures/``
   assert byte-identical chain digests between the two implementations.
2. It is the small, dependency-free primitive that the README's
   "Integrity guarantees" section refers to. Removing it would orphan
   the README and the cross-language tests.
3. It is the in-process backend for unit tests and the e2e research
   cycle, where a full Postgres dependency would be overkill.

The **production** belief service is ``ironroot.beliefs.BeliefService``
— Postgres-backed, concurrency-safe (Phase 1.2 advisory lock), with
typed observation/hypothesis/violation/prediction writers. The two
implementations are deliberately *not* unified behind a shared
Protocol: they serve different roles. ``AppendOnlyBeliefStore`` is the
algorithm; ``BeliefService`` is the production system that applies that
algorithm against a real database under concurrent writers.

Test ``tests/unit/test_append_only_store_parity.py`` pins both
implementations to the same chain-digest output for an equivalent
input, so future drift between them is caught early.
"""

from dataclasses import dataclass

from ironroot.domain.ids import generate_id, hash_content
from ironroot.domain.time import now_iso


@dataclass(frozen=True)
class BeliefRecord:
    """immutable belief record with hash chain."""

    belief_id: str
    content_hash: str
    parent_hash: str | None
    agent_id: str
    run_id: str
    content: bytes
    confidence: float
    created_at: str
    evidence_artifact_ids: tuple[str, ...]


class AppendOnlyBeliefStore:
    """in-memory append-only belief store with hash chain."""

    def __init__(self) -> None:
        self._beliefs: dict[str, BeliefRecord] = {}
        self._chain: list[str] = []
        self._hash_to_id: dict[str, str] = {}

    def append(
        self,
        content: bytes,
        agent_id: str,
        run_id: str,
        confidence: float,
        evidence_artifact_ids: tuple[str, ...] = (),
    ) -> BeliefRecord:
        """appends a new belief, returns the record."""
        belief_id = generate_id("bel")
        content_hash = hash_content(content)

        parent_hash = self._chain[-1] if self._chain else None

        record = BeliefRecord(
            belief_id=belief_id,
            content_hash=content_hash,
            parent_hash=parent_hash,
            agent_id=agent_id,
            run_id=run_id,
            content=content,
            confidence=confidence,
            created_at=now_iso(),
            evidence_artifact_ids=evidence_artifact_ids,
        )

        self._beliefs[belief_id] = record
        self._chain.append(content_hash)
        self._hash_to_id[content_hash] = belief_id

        return record

    def get(self, belief_id: str) -> BeliefRecord | None:
        """retrieves a belief by id."""
        return self._beliefs.get(belief_id)

    def get_by_hash(self, content_hash: str) -> BeliefRecord | None:
        """retrieves a belief by content hash."""
        belief_id = self._hash_to_id.get(content_hash)
        if belief_id:
            return self._beliefs.get(belief_id)
        return None

    def verify_chain(self) -> bool:
        """verifies the hash chain integrity."""
        for i, content_hash in enumerate(self._chain):
            belief_id = self._hash_to_id.get(content_hash)
            if not belief_id:
                return False

            record = self._beliefs.get(belief_id)
            if not record:
                return False

            # verify content matches hash
            actual_hash = hash_content(record.content)
            if actual_hash != content_hash:
                return False

            # verify parent pointer
            expected_parent = self._chain[i - 1] if i > 0 else None
            if record.parent_hash != expected_parent:
                return False

        return True

    def list_all(self) -> list[BeliefRecord]:
        """returns all beliefs in chain order."""
        result = []
        for content_hash in self._chain:
            belief_id = self._hash_to_id.get(content_hash)
            if belief_id:
                record = self._beliefs.get(belief_id)
                if record:
                    result.append(record)
        return result

    def __len__(self) -> int:
        return len(self._beliefs)
