# Author: Bradley R. Kinnard
"""unit tests for id generation and hashing."""

from ironroot.domain.ids import generate_id, hash_content, verify_hash


class TestGenerateId:
    """tests for id generation."""

    def test_generates_prefixed_id(self) -> None:
        """id has correct prefix."""
        run_id = generate_id("run")
        assert run_id.startswith("run_")

    def test_ids_are_unique(self) -> None:
        """consecutive ids are different."""
        ids = [generate_id("run") for _ in range(100)]
        assert len(set(ids)) == 100

    def test_all_prefixes_work(self) -> None:
        """all valid prefixes produce valid ids."""
        prefixes = ["run", "agt", "bel", "art", "str", "inc", "gat"]
        for prefix in prefixes:
            result = generate_id(prefix)  # type: ignore[arg-type]
            assert result.startswith(f"{prefix}_")


class TestHashing:
    """tests for content hashing."""

    def test_same_content_same_hash(self) -> None:
        """identical content produces identical hash."""
        data = b"test content"
        hash1 = hash_content(data)
        hash2 = hash_content(data)
        assert hash1 == hash2

    def test_different_content_different_hash(self) -> None:
        """different content produces different hash."""
        hash1 = hash_content(b"content a")
        hash2 = hash_content(b"content b")
        assert hash1 != hash2

    def test_verify_hash_correct(self) -> None:
        """verification passes for correct hash."""
        data = b"test data"
        content_hash = hash_content(data)
        assert verify_hash(data, content_hash)

    def test_verify_hash_incorrect(self) -> None:
        """verification fails for wrong hash."""
        data = b"test data"
        wrong_hash = hash_content(b"other data")
        assert not verify_hash(data, wrong_hash)

    def test_hash_is_hex_string(self) -> None:
        """hash is a valid hex string."""
        result = hash_content(b"test")
        assert all(c in "0123456789abcdef" for c in result)
        assert len(result) == 64  # sha256 produces 64 hex chars
