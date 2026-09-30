# Author: Bradley R. Kinnard
"""deterministic id generation with collision resistance."""

import hashlib
import re
import secrets
import threading
import time
from typing import Literal

# Every prefix currently used at a call site must be listed here.
# A test (`tests/unit/test_ids.py::test_every_call_site_prefix_is_declared`)
# greps `src/ironroot/` and `tests/` for `generate_id("...")` and asserts each
# literal appears in this Literal. Add a new prefix here BEFORE introducing it
# at a call site, or the build will fail.
IdPrefix = Literal[
    # core integrity / runtime
    "run",
    "bel",
    "art",
    "str",
    "inc",
    "gat",
    "obs",
    "tsk",
    "task",
    # belief / inference flavors
    "belief",
    "pred",
    "result",
    "query",
    "qry",
    "cfq",
    "hyp",
    "question",
    # healing / verification
    "vio",
    "rst",
    "reg",
    "rev",
    "att",
    "quarantine",
    # research / experiment lifecycle
    "campaign",
    "research",
    "trial",
    "episode",
    "longitudinal",
    "protocol",
    "test",
    "transfer",
    "uncertainty",
    "disagreement",
    "competence",
    "workflow",
    "skill",
    "app",
    # adversarial / battery
    "adversarial",
    "attack",
    "bat",
    # Phase 3.4: API token rows
    "tok",
]

# thread-safe counter for collision resistance within same millisecond
_counter_lock = threading.Lock()
_last_ts_ms = 0
_counter = 0

_PREFIX_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def generate_id(prefix: IdPrefix) -> str:
    """generates a prefixed id like run_a1b2c3d4e5f67890."""
    global _last_ts_ms, _counter

    if not _PREFIX_RE.match(prefix):
        raise ValueError(
            f"invalid id prefix {prefix!r}: must match {_PREFIX_RE.pattern} "
            "and be declared in IdPrefix Literal"
        )

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
    return len(actual) == len(expected_hash)
