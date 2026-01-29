# IRONROOT

> **Irreversible Research Ecology for Robust Agent Evolution**

<div align="center">

![Python](https://img.shields.io/badge/Python-3.12+-3776ab?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169e1?style=for-the-badge&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-dc382d?style=for-the-badge&logo=redis&logoColor=white)
![React](https://img.shields.io/badge/React-61dafb?style=for-the-badge&logo=react&logoColor=black)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

**140 tests passing** · **51%+ coverage** · **Strict quality gates**

</div>

---

## What This Is

A system for running AI agents that must prove their work is correct before they can evolve.

Agents run in supervised loops. They propose changes, build implementations, write tests, and verify each other's work. Memory is write-once - you can add new records but never edit old ones. Every file is stored by its content hash, so tampering is obvious. Agents that fail lose resources permanently. There are no resets.

When something breaks, the system stops accepting changes, rolls back to the last good state, runs a repair process, and adds a new test to prevent it from happening again.

When agents evolve, they do so through explicit versioned strategies that must pass all verification gates before promotion. No hidden prompt changes, no silent drift.

**This is not a chatbot.** It is a research platform for building agents that improve through hard evidence and adversarial testing.

---

## 📐 Architecture

```mermaid
graph TD
    subgraph Gateway
        A[FastAPI API]
        S[React UI]
    end

    subgraph Orchestration
        B[Run Service]
        C[Supervisor State Machine]
        K[Kill Switch]
    end

    subgraph Agents
        D[Proposer]
        E[Builder]
        F[Tester]
        G[Verifier]
        H[Auditor]
        I[Repair]
    end

    subgraph Storage
        J[(PostgreSQL)]
        L[(Artifact Store)]
    end

    subgraph Verification
        N[Gate Service]
        O{Pass?}
        P[Promote]
        Q[Contain + Rollback]
    end

    A --> B
    S --> A
    B --> C
    C --> D & E & F & G & H
    C --> J
    C --> L
    C --> N
    N --> O
    O -->|Yes| P
    O -->|No| Q
    Q --> I
    I --> N
    K -.->|invariant break| Q
```

---

## 🔑 Core Rules

| Rule | How It Works | Code |
|------|--------------|------|
| **Memory is write-once** | You can add beliefs but never edit or delete them. Hash chains verify nothing was tampered with. | [`append_only_store.py`](src/ironroot/cognition/memory/append_only_store.py) |
| **Files are stored by content hash** | Same content = same path. If you change one byte, the hash changes. Tampering is obvious. | [`artifacts.py`](src/ironroot/storage/artifacts.py) |
| **Budgets are enforced** | Agents have limited steps, tool calls, and memory writes. When they run out, they stop. No exceptions. | [`budgets.py`](src/ironroot/orchestration/budgets.py) |
| **Promotion requires passing tests** | A strategy cannot be promoted unless all verification gates pass first. | [`strategy_service.py`](src/ironroot/cognition/strategies/strategy_service.py) |
| **Failures trigger containment** | When something breaks, the system freezes changes and starts recovery. | [`kill_switch.py`](src/ironroot/orchestration/kill_switch.py) |

---

## 📦 Module Map

<details>
<summary><strong>🎛️ Orchestration</strong> — Run lifecycle, budgets, self-healing</summary>

| Module | Purpose |
|--------|---------|
| [`supervisor.py`](src/ironroot/orchestration/supervisor.py) | State machine: init → propose → build → test → verify → audit → decide |
| [`budgets.py`](src/ironroot/orchestration/budgets.py) | Hard limits on steps, tool calls, memory writes |
| [`kill_switch.py`](src/ironroot/orchestration/kill_switch.py) | Invariant break triggers containment |
| [`run_service.py`](src/ironroot/orchestration/run_service.py) | CRUD for runs with budget tracking |
| [`healing.py`](src/ironroot/orchestration/healing.py) | Containment → rollback → repair → retest flow |
| [`incidents.py`](src/ironroot/orchestration/incidents.py) | Incident types and severity mapping |

</details>

<details>
<summary><strong>💾 Storage</strong> — Content-addressed artifacts, models</summary>

| Module | Purpose |
|--------|---------|
| [`artifacts.py`](src/ironroot/storage/artifacts.py) | SHA256 hashing, write-once enforcement |
| [`artifact_service.py`](src/ironroot/storage/artifact_service.py) | Store/retrieve with integrity verification |
| [`models.py`](src/ironroot/storage/models.py) | SQLAlchemy ORM: runs, beliefs, agents, incidents, gates, strategies |
| [`postgres.py`](src/ironroot/storage/postgres.py) | Session factory and base model |

</details>

<details>
<summary><strong>🧠 Cognition</strong> — Beliefs, strategies, memory</summary>

| Module | Purpose |
|--------|---------|
| [`append_only_store.py`](src/ironroot/cognition/memory/append_only_store.py) | Immutable belief records with hash chain |
| [`belief_service.py`](src/ironroot/cognition/memory/belief_service.py) | DB persistence, chain verification |
| [`contradiction.py`](src/ironroot/cognition/memory/contradiction.py) | Links conflicting beliefs as new events |
| [`mutation.py`](src/ironroot/cognition/strategies/mutation.py) | Bounded strategy changes with provenance |
| [`strategy_service.py`](src/ironroot/cognition/strategies/strategy_service.py) | Gate-blocked promotion, multi-objective scoring |
| [`registry.py`](src/ironroot/cognition/strategies/registry.py) | In-memory strategy version management |

</details>

<details>
<summary><strong>✅ Verification</strong> — Gates, replay, integrity</summary>

| Module | Purpose |
|--------|---------|
| [`gate_service.py`](src/ironroot/verification/gate_service.py) | Executes replay, integrity, invariant, regression gates |
| [`replay.py`](src/ironroot/verification/replay.py) | Same inputs + seed = equivalent trace digest |
| [`regression_gate.py`](src/ironroot/verification/regression_gate.py) | All gates must pass for promotion |
| [`integrity.py`](src/ironroot/verification/integrity.py) | Stored bytes hash equals recorded hash |

</details>

<details>
<summary><strong>🤖 Agents</strong> — Specialized workers with budgets</summary>

| Agent | Scope |
|-------|-------|
| [`base.py`](src/ironroot/agents/base.py) | Budgets, penalties, tool access |
| [`proposer.py`](src/ironroot/agents/proposer.py) | Proposes cognitive layer changes |
| [`builder.py`](src/ironroot/agents/builder.py) | Implements under stable contracts |
| [`tester.py`](src/ironroot/agents/tester.py) | Writes tests against claims |
| [`verifier.py`](src/ironroot/agents/verifier.py) | Attempts falsification |
| [`auditor.py`](src/ironroot/agents/auditor.py) | Trace integrity, policy compliance |
| [`repair.py`](src/ironroot/agents/repair.py) | Minimal diff + mandatory new test |

</details>

---

## 🚀 Quick Start

```bash
# Clone
git clone https://github.com/moonrunnerkc/ironroot.git && cd ironroot

# Python 3.12+ virtual environment
python3.12 -m venv .venv && source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Environment config
cp .env.example .env

# Start infrastructure (postgres + redis)
./scripts/dev_up.sh

# Run migrations
alembic upgrade head

# Verify: 140 tests, 50%+ coverage
pytest -q --cov=src/ironroot --cov-fail-under=50

# Start API server
./scripts/run_once.sh
```

---

## 🔌 API Reference

Base: `/api/v1`

| Endpoint | Method | Purpose |
|:---------|:------:|:--------|
| `/health` | `GET` | DB, queue, store connectivity |
| `/runs` | `POST` | Create run with seed, budgets, gates |
| `/runs/{id}` | `GET` | Status, phase, budgets, failures |
| `/runs/{id}/start` | `POST` | Start orchestration |
| `/runs/{id}/stop` | `POST` | Hard stop, freeze commits |
| `/runs/{id}/gates/execute` | `POST` | Execute gate suite |
| `/runs/{id}/gates/status` | `GET` | Pass/fail with artifact evidence |
| `/artifacts/{id}` | `GET` | Metadata + download |
| `/beliefs` | `GET` | List with filters |
| `/beliefs/{id}/contradictions` | `GET` | Linked contradiction events |
| `/strategies` | `GET` `POST` | List or register |
| `/strategies/{id}/promote` | `POST` | Promote if gate passed |

---

## 🧪 Testing

```bash
pytest tests/unit -v              # Unit tests
pytest tests/integration -v       # Requires postgres/redis
pytest tests/e2e -v               # Full research cycle
pytest --cov=src/ironroot         # Coverage report
```

---

## ❓ Skeptic's Corner

<details>
<summary><strong>Why write-once memory?</strong></summary>

If agents can edit their past beliefs, you lose the ability to see what they actually thought and when. The [`append_only_store.py`](src/ironroot/cognition/memory/append_only_store.py) prevents any updates or deletes. When an agent changes its mind, that's recorded as a new belief linked to the old one. The hash chain means if anyone tampers with history, the math breaks and you'll know.

</details>

<details>
<summary><strong>Why store files by hash?</strong></summary>

If you use random IDs, you're trusting that the database correctly tracks what's what. If you use content hashes, the file's identity is its content - same bytes always means same hash. The [`artifacts.py`](src/ironroot/storage/artifacts.py) module stores everything by its SHA256 hash. Change one byte, the hash changes, the path changes. You can't silently modify a file.

</details>

<details>
<summary><strong>Why use explicit state machines?</strong></summary>

When code "just runs" without clear phases, it's hard to know where things went wrong. The [`supervisor.py`](src/ironroot/orchestration/supervisor.py) defines every step: init, propose, build, test, verify, audit, decide. Each transition has rules. The kill switch can stop execution at any point. If you replay with the same inputs, you get the same path through the machine.

</details>

<details>
<summary><strong>Why have separate verifiers?</strong></summary>

Agents shouldn't grade their own work - that's a conflict of interest. The [`verifier.py`](src/ironroot/agents/verifier.py) exists specifically to try to break proposals. The [`auditor.py`](src/ironroot/agents/auditor.py) checks that the execution trace is intact. Neither one benefits from saying "yes" to bad work. The [`regression_gate.py`](src/ironroot/verification/regression_gate.py) ensures nothing gets promoted without passing these adversarial checks.

</details>

<details>
<summary><strong>Why permanent penalties?</strong></summary>

If agents can just retry after failing, they learn that failure is cheap. The [`budgets.py`](src/ironroot/orchestration/budgets.py) tracks lifetime limits - steps, tool calls, memory writes. Fail a verification? You lose budget permanently. Get a tool revoked? It stays revoked. This pressure selects for agents that are careful and calibrated. Reckless agents run out of resources and stop.

</details>

---

<div align="center">

**MIT License** · Built for skeptical engineers

</div>
