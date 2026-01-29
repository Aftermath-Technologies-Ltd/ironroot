# Author: Bradley R. Kinnard
"""unit tests for append-only belief store."""

from ironroot.cognition.memory.append_only_store import AppendOnlyBeliefStore
from ironroot.domain.ids import hash_content


class TestAppendOnlyStore:
    """tests for append-only belief store."""

    def test_append_creates_record(self) -> None:
        """appending creates a retrievable record."""
        store = AppendOnlyBeliefStore()
        record = store.append(
            content=b"test belief",
            agent_id="agt_test",
            run_id="run_test",
            confidence=0.9,
        )

        assert record.belief_id.startswith("bel_")
        assert record.content == b"test belief"
        assert record.agent_id == "agt_test"
        assert record.run_id == "run_test"
        assert record.confidence == 0.9

    def test_first_belief_has_no_parent(self) -> None:
        """first belief in chain has null parent."""
        store = AppendOnlyBeliefStore()
        record = store.append(b"first", "agt", "run", 1.0)
        assert record.parent_hash is None

    def test_subsequent_beliefs_chain_to_parent(self) -> None:
        """subsequent beliefs reference parent hash."""
        store = AppendOnlyBeliefStore()
        first = store.append(b"first", "agt", "run", 1.0)
        second = store.append(b"second", "agt", "run", 1.0)

        assert second.parent_hash == first.content_hash

    def test_content_hash_is_correct(self) -> None:
        """content hash matches actual hash of content."""
        store = AppendOnlyBeliefStore()
        content = b"test content"
        record = store.append(content, "agt", "run", 1.0)

        expected_hash = hash_content(content)
        assert record.content_hash == expected_hash

    def test_get_by_id(self) -> None:
        """can retrieve belief by id."""
        store = AppendOnlyBeliefStore()
        record = store.append(b"test", "agt", "run", 1.0)

        retrieved = store.get(record.belief_id)
        assert retrieved is not None
        assert retrieved.content == b"test"

    def test_get_by_hash(self) -> None:
        """can retrieve belief by content hash."""
        store = AppendOnlyBeliefStore()
        record = store.append(b"test", "agt", "run", 1.0)

        retrieved = store.get_by_hash(record.content_hash)
        assert retrieved is not None
        assert retrieved.belief_id == record.belief_id

    def test_verify_chain_empty(self) -> None:
        """empty store has valid chain."""
        store = AppendOnlyBeliefStore()
        assert store.verify_chain()

    def test_verify_chain_single(self) -> None:
        """single belief store has valid chain."""
        store = AppendOnlyBeliefStore()
        store.append(b"only", "agt", "run", 1.0)
        assert store.verify_chain()

    def test_verify_chain_multiple(self) -> None:
        """multi-belief chain verifies correctly."""
        store = AppendOnlyBeliefStore()
        for i in range(10):
            store.append(f"belief {i}".encode(), "agt", "run", 1.0)
        assert store.verify_chain()

    def test_list_all_preserves_order(self) -> None:
        """list_all returns beliefs in chain order."""
        store = AppendOnlyBeliefStore()
        for i in range(5):
            store.append(f"belief {i}".encode(), "agt", "run", 1.0)

        all_beliefs = store.list_all()
        assert len(all_beliefs) == 5
        for i, belief in enumerate(all_beliefs):
            assert belief.content == f"belief {i}".encode()

    def test_len(self) -> None:
        """len returns count of beliefs."""
        store = AppendOnlyBeliefStore()
        assert len(store) == 0

        store.append(b"one", "agt", "run", 1.0)
        assert len(store) == 1

        store.append(b"two", "agt", "run", 1.0)
        assert len(store) == 2
