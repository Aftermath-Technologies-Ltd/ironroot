# Author: Bradley R. Kinnard
"""deterministic id generation with collision resistance."""

import hashlib
import secrets
import threading
import time
from typing import Literal

IdPrefix = Literal["run", "agt", "bel", "art", "str", "inc", "gat"]

# thread-safe counter for collision resistance within same millisecond
_counter_lock = threading.Lock()
_last_ts_ms = 0
_counter = 0


def generate_id(prefix: IdPrefix) -> str:
    """generates a prefixed id like run_a1b2c3d4e5f67890."""
    global _last_ts_ms, _counter

    with _counter_lock:
        ts_ms = int(time.time() * 1000)
        if ts_ms == _last_ts_ms:
            _counter += 1
        else:
            _last_ts_ms = ts_ms
            _counter = 0

        # 6 bytes timestamp + 2 bytes counter + 6 bytes random
        ts_bytes = ts_ms.to_bytes(6, "big")
        counter_bytes = (_counter & 0xFFFF).to_bytes(2, "big")
        rand_bytes = secrets.token_bytes(6)
        combined = ts_bytes + counter_bytes + rand_bytes
        suffix = combined.hex()
        return f"{prefix}_{suffix}"


def hash_content(data: bytes) -> str:
    """sha256 hash of bytes, returns hex digest."""
    return hashlib.sha256(data).hexdigest()


def verify_hash(data: bytes, expected_hash: str) -> bool:
    """constant-time hash comparison to avoid timing attacks."""
    actual = hash_content(data)
    return secrets.compare_digest(actual, expected_hash)
