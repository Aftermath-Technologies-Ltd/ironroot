# IRONROOT

A research platform for agents whose work must be reproducible and tamper-evident.

IRONROOT is a Python codebase that pairs an append-only, hash-chained belief
store with a content-addressed artifact store and a small set of verification
gates (replay, regression, falsification, invariants). It is the durable
substrate beneath several experimental subsystems (agents, orchestration,
research, evolution, self-healing) that are themselves out of scope of this
document.

This README describes only what IRONROOT actually guarantees. It makes no
claims about performance, agent capability, or readiness for use beyond
internal research.

## Components

- `src/ironroot/domain/` — ids (sha256 content hashing, UUID generation),
  errors, monotonic time, named invariants.
- `src/ironroot/cognition/memory/append_only_store.py` — `BeliefRecord` and
  `AppendOnlyBeliefStore`. Each record stores `content_hash`, `parent_hash`,
  and the chain is verified by recomputing hashes and link relations.
- `src/ironroot/storage/artifacts.py` — content-addressed filesystem store
  laid out as `{base}/{hash[:4]}/{hash}/content`, with write-once semantics
  enforced by hash equality checks on rewrite attempts.
- `src/ironroot/verification/` — `integrity.py`, `replay.py`,
  `regression_gate.py`, `falsification.py`, `gate_service.py`. These define
  the gates a candidate change must pass before it is allowed to mutate state.
- `src/ironroot/api/`, `src/ironroot/orchestration/`, `src/ironroot/agents/`,
  `src/ironroot/llm/`, `src/ironroot/research/`, `src/ironroot/agi/`,
  `src/ironroot/cognition/strategies/`, `src/ironroot/cognition/planning/`,
  `src/ironroot/world_models/`, `src/ironroot/evolution/`,
  `src/ironroot/healing/` — research subsystems built on top of the integrity
  core. They are intentionally not described here.
- `src/ironroot/ui_backend/` — WebSocket event bridge. It has no current
  consumer (the previous React UI has been removed). Retained for future use.

## Integrity guarantees

The integrity guarantees IRONROOT enforces are:

1. **Append-only belief chain.** `AppendOnlyBeliefStore.append` computes
   `content_hash = sha256(content)`, sets `parent_hash` to the previous head,
   and refuses to alter prior records. `verify_chain` recomputes every hash
   and link relation from genesis.
2. **Content-addressed artifacts.** `ArtifactStore.store(data)` writes to
   `{base}/{hash[:4]}/{hash}/content`. If the path already exists, the bytes
   on disk must hash to the same value or `IntegrityError` is raised. Writes
   are otherwise rejected — there is no in-place update.
3. **Verification gates.** A change is admitted only if the configured
   `gate_service` reports that replay, regression, falsification, and named
   invariants all pass.

Everything else in this repository is research code that builds on these
primitives.

## TypeScript package: `@ironroot/core`

A TypeScript port of the integrity primitives lives in `packages/core-ts/`
and is published as `@ironroot/core`. It is a 1:1 port of `domain/`,
`cognition/memory/append_only_store.py`, `storage/artifacts.py`, and the
`verification/` gates, persisted via `better-sqlite3`. It exists so that
Node consumers (e.g. Dossier) can use IRONROOT as a library rather than
shelling out to Python.

Cross-language test fixtures in `packages/core-ts/test/fixtures/` assert
byte-identical canonicalization and chain hashes between the Python and
TypeScript implementations. Both implementations must remain equivalent
under those fixtures; neither is considered a replacement for the other.

## Development

Prerequisites: Python 3.12, Docker (for Postgres/Redis), Node 18+ (only if
working on `packages/core-ts/`).

```
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
./scripts/start_all.sh   # postgres + redis + schema
./scripts/run_once.sh    # uvicorn ironroot.main:app
pytest
```

For the TypeScript package:

```
cd packages/core-ts
npm install
npm test
```

## Layout

```
src/ironroot/        Python package
packages/core-ts/    @ironroot/core (TypeScript port of integrity primitives)
tests/               pytest suite
scripts/             dev_up / dev_down / start_all / run_once / seed_demo_data
artifacts/           local artifact store (gitignored content)
data/                local Postgres/Redis state (gitignored)
```

## License

MIT (per `pyproject.toml`).
