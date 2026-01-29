# IRONROOT: Irreversible Research Ecology for Robust Agent Evolution

## Copilot and contributor rules (override everything)

These rules override everything else in this repo, including any other instruction files. If something below conflicts with another rule, follow this section.

### 1. Global principles
- Correct false assumptions first, before proposing solutions.
- If something is misclassified, mislabeled, or overstated, call it out explicitly.
- No hallucinations. If evidence is missing, say so.
- If a claim cannot be proven, frame it as a goal or hypothesis, never as fact.
- Prefer hard constraints, invariants, and verification over best-effort behavior.
- Favor systems that fail loudly rather than silently degrade.
- Determinism and replayability are first-class concerns.
- Write for skeptical engineers, not marketing readers.

### 2. Language and writing style rules
- Serious, direct, professional tone.
- No fluff. No motivational filler. No hype language.
- Dark humor is acceptable only when it clarifies reality, not as decoration.
- Human-written cadence is fine. Slightly imperfect sentence structure is fine.
- Avoid over-polished or corporate phrasing.
- Never use em dashes.
- Avoid buzzwords unless they are precisely defined.
- Use common, literal words. Avoid jargon unless it is necessary and defined.
- Do not anthropomorphize systems or imply AI thinks like a human.
- Start with the practical outcome first, then explain how.

### 3. Claims and assertions
- Every strong claim must be testable, falsifiable, or explicitly marked as an objective.
- No guarantees unless they are enforced by code or protocol.
- No novelty claims unless novelty is scoped and defensible.
- Avoid words like magic, breakthrough, revolutionary, or just works.
- If external systems are involved, never promise behavior you do not control.

### 4. Documentation rules (Markdown, guides, READMEs)
- Keep the number of Markdown files minimal. Only what is commonly expected.
- Prefer one primary README whenever possible.
- Build guides must be step-by-step, implementation-real, and free of hand-waving.
- No placeholder text. No TODO. No example-only paths.
- If something is optional, state why and when.
- State system boundaries and non-goals explicitly.
- Do not include large code blocks in build guides.
- Small snippets are allowed only to illustrate structure or commands.
- Docs must align with what can actually be built today.

### 5. Coding rules (non-negotiable)
- No pseudocode unless explicitly requested.
- No placeholders. Ever.
- Code must be production-grade or not shown at all.
- Follow strict formatting and linting: ruff, black, mypy, pytest.
- High coverage requirements. Never lower coverage to get green.
- Deterministic behavior where possible.
- Explicit error handling. No silent failures.
- Prefer explicit state machines over implicit flow.
- No hidden retries.
- No mutable global state.
- Comments must be lowercase, human-written, and explain why, not what.
- Docstrings follow repo conventions: concise purpose only, no argument descriptions.
- DRY and SOLID principles enforced.
- Tests are part of the feature, not an afterthought.

### 6. System design rules
- Use explicit interfaces and contracts between components.
- No prompt soup architectures.
- No silent coupling between layers.
- Evolution or learning must be observable and auditable.
- Memory must have structure, limits, and integrity checks.
- Any self-modification must be bounded, logged, and reversible only when explicitly designed.
- Prefer append-only or versioned state over mutable state.
- Budgets are mandatory for time, steps, tool calls, and memory writes.

### 7. Verification and testing philosophy
- Verification is not vibes.
- Verification must produce artifacts.
- Every gate must output logs, hashes, and reproducible identifiers.
- Replayability matters more than peak performance.
- Add regression tests after failures.
- Tests must be adversarial, not friendly.
- If something passes, you must be able to show why.
- If something fails, you must be able to show where.

### 8. UI and UX rules
- UI is not a demo layer.
- UI must reflect backend truth exactly.
- Every pass or success indicator must link to evidence.
- No UI-only computed state for correctness.
- Avoid flashy visuals that hide missing data.
- Favor clarity, traceability, and inspectability.
- UI actions must be reproducible via API.
- If the UI shows a result, CI must be able to reproduce it.

### 9. Model and AI usage rules
- No AI tells in public-facing content.
- No generic LLM phrasing.
- Do not imply intelligence where there is process.
- Models are tools, not actors.
- If a model is used, specify version, scope, and constraints.
- Avoid claims of autonomy without kill switches.
- Always design for drift detection.

### 10. Personal preference enforcement
- Always point out blind spots before proceeding.
- Never let false assumptions carry forward.
- Ask before advancing scope or phases.
- Use naming conventions consistently once established.
- Maintain continuity across sessions and projects.
- Treat every system as something a hostile reviewer will inspect.

### 11. One-line summary
If a skeptical senior systems engineer cannot tear it apart in five minutes, it is not finished.

## What this is
IRONROOT targets a production-grade agent ecosystem designed to evolve reliable cognitive behaviors under adversarial pressure. It runs multi-agent research loops where agents must earn survival by producing verifiable, reproducible work. Memory is designed to be append-only and tamper-evident. Errors are designed to have irreversible consequences. Self-healing is implemented as detection, containment, rollback, and repair, with permanent test additions after failures. Self-evolving is implemented as controlled mutation and selection over explicitly versioned strategies, not hidden prompt soup.

This is not a chatbot platform. It is an engineering system for iterating on cognitive layers and agent strategies with hard evidence, auditability, and deterministic replay.

---

## Design goals
- Deterministic replay at the run level: same inputs and seed produce the same trace and artifacts within a defined tolerance boundary.
- Append-only belief history with tamper evidence.
- Irreversible consequences for falsehoods and violations.
- Adversarial verification and regression tests as the gate to evolution.
- Minimal operational surface area, no fake stubs, no demo-only paths.
- A UI that is useful, not theater: every displayed metric links to an artifact and a test.

---

## Core concepts

### Agents
Agents are specialized workers with strict scopes and budgets:
- proposer: proposes changes to cognitive layers or strategies
- builder: implements changes in code under stable contracts
- tester: writes or hardens tests aimed at the claims
- verifier: attempts falsification, counterexamples, and regression breaks
- auditor: checks trace integrity, determinism markers, and policy compliance
- supervisor: orchestrates, enforces budgets, and decides accept or kill

Agents do not self-grade. Verifiers and auditors are adversarial by design.

### Beliefs and memory
Beliefs are append-only records. Every belief write includes:
- content hash
- parent hash pointer
- agent id
- run id
- timestamp
- confidence score
- evidence pointers (artifact ids)
- contradiction links (if detected)

Beliefs are never edited. Contradictions are recorded as new events.

### Irreversible penalties
When an agent fails verification or violates policy:
- reduce lifetime budget (tokens, steps, tool calls)
- revoke tools (eg external retriever)
- restrict task classes (eg cannot propose changes anymore)
- eventually terminate the agent instance
- record the incident with evidence and add a regression test

No resets. No “just try again.” Repair can happen, but consequences remain.

### Self-healing
Self-healing is not magic. It is:
1. detect: invariant failure, trace mismatch, contradiction spike, test failure
2. contain: freeze commits, quarantine memory segment, revoke tool access
3. rollback: restore last known-good snapshot, re-run replay checks
4. repair: spawn repair plan with minimal diff and new test requirements
5. retest: run full gate suite
6. learn: permanently add tests and update risk rules

### Self-evolution
Evolution operates on explicit strategy artifacts:
- strategy packages define policies for planning, memory writes, confidence calibration, tool usage, and abstention thresholds
- mutation generates small bounded variations
- selection uses multi-objective scoring focused on correctness, reproducibility, and efficiency
- inheritance is lossy and policy-limited, never copying raw hidden state

Evolution is always gated by tests and audits.

---

## System boundaries and claims
What IRONROOT can claim if built to this guide:
- It will run a real agent ecology, produce real artifacts, and enforce real gates.
- It will make failures obvious and expensive, preventing silent degradation.
- It will evolve strategy variants that measurably improve defined task suites.

What IRONROOT will not claim:
- It will “discover AGI” automatically.
- It will prove natural language claims as formal theorems unless you formalize them.
- It will outperform frontier labs on open-ended science without rigorous harnesses.

---

## Tech stack
- Python 3.12+
- FastAPI for API
- PostgreSQL for metadata and run registry
- Object storage for artifacts (local filesystem is supported, S3-compatible optional)
- Redis for queue and ephemeral coordination
- Celery or Dramatiq for background execution (choose one, do not mix)
- React + Vite UI, talking only to the API
- Pytest for tests, coverage enforced
- ruff + black + mypy for static quality gates
- Optional: Docker for dev and deployment

---

## Repository layout (single repo, no sprawling docs)
You will have one primary doc: this README.md. Keep additional MD files to the usual minimum:
- README.md (this file)
- CONTRIBUTING.md (quality rules, local dev, test commands)
- SECURITY.md (how to report issues)
Everything else is code, config, or tests.

---

## File structure (complete)
ironroot/
  README.md
  CONTRIBUTING.md
  SECURITY.md
  pyproject.toml
  ruff.toml
  mypy.ini
  .env.example
  docker-compose.yml
  scripts/
    dev_up.sh
    dev_down.sh
    run_once.sh
    seed_demo_data.sh
  src/
    ironroot/
      __init__.py
      main.py
      settings.py
      logging/
        __init__.py
        configure.py
      api/
        __init__.py
        deps.py
        router.py
        routes/
          __init__.py
          health.py
          runs.py
          artifacts.py
          beliefs.py
          strategies.py
          agents.py
          tests.py
          ui.py
      domain/
        __init__.py
        ids.py
        time.py
        errors.py
        policies.py
        invariants.py
      storage/
        __init__.py
        artifacts.py
        postgres.py
        migrations/
      orchestration/
        __init__.py
        supervisor.py
        budgets.py
        queue.py
        lifecycle.py
        kill_switch.py
      agents/
        __init__.py
        base.py
        proposer.py
        builder.py
        tester.py
        verifier.py
        auditor.py
        repair.py
      cognition/
        __init__.py
        memory/
          __init__.py
          append_only_store.py
          contradiction.py
          retrieval.py
        strategies/
          __init__.py
          registry.py
          scoring.py
          mutation.py
          selection.py
        planning/
          __init__.py
          planner.py
          abstention.py
          tool_policy.py
      verification/
        __init__.py
        replay.py
        integrity.py
        invariants.py
        falsification.py
        regression_gate.py
      ui_backend/
        __init__.py
        events.py
        websocket.py
  ui/
    package.json
    vite.config.ts
    tsconfig.json
    src/
      main.tsx
      app.tsx
      api/
        client.ts
        types.ts
      pages/
        dashboard.tsx
        run_detail.tsx
        strategies.tsx
        beliefs.tsx
        tests.tsx
      components/
        run_table.tsx
        artifact_viewer.tsx
        belief_graph.tsx
        diff_view.tsx
        gate_status.tsx
      styles/
        app.css
  tests/
    unit/
      test_ids.py
      test_append_only_store.py
      test_integrity_hashing.py
      test_budgeting.py
      test_strategy_registry.py
    integration/
      test_api_runs.py
      test_run_lifecycle.py
      test_artifact_storage.py
      test_regression_gate.py
      test_ui_api_contracts.py
    e2e/
      test_full_research_cycle.py
  data/
    corpora/
      pinned/
        README.txt
    baselines/
      README.txt
  artifacts/
    .gitkeep

Notes:
- data/corpora/pinned contains only legally redistributable corpora or pointers and hashes. No license landmines.
- artifacts/ is for local dev only. Production uses object storage.

---

## API structure (FastAPI)
All endpoints are versioned. All responses include request_id and run_id where relevant. No “best effort” success. Either it is committed with evidence or it is rejected.

Base: /api/v1

### Health
GET /health
- returns service readiness, DB connectivity, queue connectivity, artifact store connectivity

### Runs
POST /runs
- create a run
- input: run_config (seed, budgets, strategy_set, corpus pin, gates)
- output: run_id

POST /runs/{run_id}/start
- starts orchestration for the run

GET /runs/{run_id}
- returns run status, phase, budgets remaining, gate status, failure reasons

GET /runs/{run_id}/trace
- returns a paginated trace index (events only), not massive blobs

POST /runs/{run_id}/stop
- hard stops the run and freezes commits, leaves trace intact

### Artifacts
GET /artifacts/{artifact_id}
- returns metadata and a signed download url or local path reference

GET /runs/{run_id}/artifacts
- lists artifacts by type (report, trace bundle, diffs, test logs)

### Beliefs
GET /beliefs
- list beliefs with filters: agent_id, run_id, topic tags

GET /beliefs/{belief_id}
- returns belief content, hashes, evidence pointers

GET /beliefs/{belief_id}/contradictions
- returns linked contradiction events

### Strategies
GET /strategies
- list available strategy versions and capabilities

POST /strategies
- register a new strategy package version
- requires: signed manifest, pinned dependencies, policy declaration

GET /strategies/{strategy_id}
- returns manifest, scoring history, failure incidents

POST /strategies/{strategy_id}/promote
- moves strategy to eligible set, only if regression gate passed

### Agents
GET /agents
- list agents, penalties, tool access, survival stats

GET /agents/{agent_id}
- details and incident history

### Tests and gates
GET /tests
- lists test suites and last results

POST /runs/{run_id}/gates/execute
- executes gate suite against the run artifacts
- produces a gate artifact bundle and stores it

GET /runs/{run_id}/gates/status
- pass or fail, with evidence artifact ids

### UI events
GET /ui/events/stream (websocket)
- pushes run events and gate updates in real time
- events are derived from the trace, not separate state

---

## Data model (minimal, real, auditable)
Postgres tables:
- runs: configuration, seed, status, timestamps
- agents: identity, role, budgets, penalties
- beliefs: append-only records, hashes, evidence pointers
- contradictions: links between beliefs and contradiction events
- artifacts: metadata, content hash, store location, created_by
- strategies: versioned manifests, policy declarations
- incidents: failures, penalties, linked evidence
- gates: gate runs, results, linked artifacts

Artifact store layout (content-addressed):
- artifacts/{sha256_prefix}/{sha256_full}/{type}/{filename}

Everything is content-hashed. The DB stores hashes and pointers, not truth.

---

## UI (useful and wired to evidence)
UI goal: a skeptical engineer should be able to click any “pass” badge and land on the exact evidence artifact and test run that produced it.

### UI pages
1. Dashboard
- active runs table
- gate status per run
- last incident per run
- “replay determinism check” button

2. Run detail
- timeline view of trace events
- budgets and penalties over time
- artifact list with hashes
- “download run bundle” button

3. Beliefs
- belief list with filters
- belief detail with hash chain
- contradiction graph view

4. Strategies
- strategy versions
- score history and failures
- promote button disabled unless gate passed

5. Tests
- suites and last results
- test logs artifact viewer
- coverage and static checks status

### Evidence wiring rules
- UI never shows computed pass states without also showing:
  - gate artifact id
  - test run id
  - content hash
- UI reads gate status only from /runs/{run_id}/gates/status
- All UI “download” actions are signed URLs from the API
- Websocket events are derived from trace events, not separate UI state

---

## Build guide (no implementation code, only tiny example snippets)

### Phase 0: Repo bootstrap and quality gates
Goal: lock quality rules first so you cannot “finish later” and ship slop.

Steps:
1. Create repo and the file structure above.
2. Configure ruff, black, mypy, pytest, coverage gates in pyproject.toml.
3. Add pre-commit hooks for formatting and linting.
4. Add CI workflow that runs:
   - ruff
   - black check
   - mypy
   - pytest with coverage gate

Evidence required:
- CI green on first commit
- Coverage threshold enforced (set it high and do not lower it later)

Example snippet (command only):
- pytest -q --cov=src/ironroot --cov-fail-under=95

### Phase 1: Artifact store and hashing
Goal: everything that matters is content-addressed and tamper-evident.

Steps:
1. Implement artifact storage module:
   - write bytes to store
   - compute sha256
   - enforce “write once” by hash path
2. Add metadata table and API endpoints for listing and fetching metadata.
3. Implement integrity check:
   - stored bytes hash must equal recorded hash
4. Add unit tests for:
   - same content produces same hash
   - tamper detection triggers failure

Evidence required:
- unit tests for integrity pass
- integration test that stores then reads artifact, verifies hash equality
- one “tamper test” that modifies bytes and confirms detection

### Phase 2: Append-only belief store and contradiction linking
Goal: beliefs are append-only and contradictions are recorded, not erased.

Steps:
1. Implement belief record schema and write path:
   - belief content
   - parent hash pointer
   - agent id, run id
   - evidence artifact ids
2. Enforce immutability:
   - no update endpoint
   - DB constraints and API refusal
3. Implement contradiction detection at the rule level first:
   - define contradiction as explicit conflict on declared propositions
   - do not start with fuzzy embedding contradictions as truth
4. Add endpoints for listing beliefs and contradictions.

Evidence required:
- test that update is impossible via API and DB layer
- test for hash chain correctness
- test that contradiction adds a new event, does not modify prior beliefs

### Phase 3: Run lifecycle and orchestration supervisor
Goal: make the system real. Runs exist, are replayable, and have budgets.

Steps:
1. Create run record, start, stop endpoints.
2. Implement supervisor state machine:
   - init
   - propose
   - build
   - test
   - verify
   - audit
   - decide
   - repair (optional)
   - finalize
3. Implement budgets:
   - max steps
   - max tool calls
   - max write operations
   - timeouts
4. Implement kill switch:
   - any invariant break halts commit and triggers containment

Evidence required:
- integration test that run progresses through phases deterministically using a fixed seed
- test that budget exhaustion halts the run
- test that stop endpoint freezes commits

### Phase 4: Verification and regression gate
Goal: evolution cannot proceed without passing objective gates.

Steps:
1. Implement replay determinism check:
   - same inputs and seed must produce equivalent trace digest
   - define equivalence tolerance clearly, store digest artifact
2. Implement invariants:
   - belief hash chain invariants
   - artifact integrity invariants
   - policy invariants (no forbidden tools used)
3. Implement regression gate suite:
   - run-level gate
   - strategy-level gate
4. Store gate results as artifacts, link them in DB.

Evidence required:
- gate execution produces a gate bundle artifact
- UI and API both show the same gate bundle hash for the same run
- failing a gate blocks strategy promotion and run acceptance

### Phase 5: Self-healing pipeline
Goal: failures trigger containment, rollback, repair, and retest, not silent continuation.

Steps:
1. Define incident types:
   - integrity failure
   - determinism mismatch
   - invariant violation
   - verification failure
2. Implement containment:
   - freeze belief commits
   - quarantine current memory segment
   - revoke suspect tools
3. Implement rollback:
   - restore last known good snapshot pointers
   - rerun replay check
4. Implement repair agent:
   - must produce a minimal change plan
   - must add at least one test that fails pre-fix and passes post-fix
5. Retest:
   - full gate suite
6. Record incident with evidence.

Evidence required:
- e2e test that injects a controlled failure and validates:
  - containment occurs
  - rollback occurs
  - repair adds a test
  - gate suite passes only after repair

### Phase 6: Self-evolution of strategies
Goal: controlled, test-gated evolution of explicit strategy artifacts.

Steps:
1. Implement strategy manifest rules:
   - pinned dependencies
   - declared capabilities
   - declared tool permissions
   - declared abstention policy
2. Implement mutation:
   - bounded changes only
   - mutation provenance recorded
3. Implement selection:
   - multi-objective scoring:
     - correctness (gate pass)
     - reproducibility (replay digest match)
     - efficiency (budgets used)
     - safety (incident rate)
4. Allow promotion only when gate suite passes.

Evidence required:
- test that mutated strategy cannot be promoted if any gate fails
- test that selection chooses a strategy that passes gates over one that is “novel” but fails correctness
- audit record shows why a strategy was promoted

### Phase 7: UI completion and contract tests
Goal: UI is not a lie layer.

Steps:
1. Implement UI pages listed above.
2. Add contract tests:
   - UI API types match backend OpenAPI schema
   - key endpoints return stable shape
3. Add end-to-end UI smoke test (headless):
   - start run
   - observe gate updates
   - open run detail
   - download artifact metadata
   - confirm hash displayed equals API hash

Evidence required:
- integration test suite includes UI API contract tests
- e2e run demonstrates UI reflects gate bundle evidence

---

## Testing strategy (counterproof, phase by phase)
You will not “feel done.” You will know it.

### Test layers
- unit tests: pure functions, hashing, budgeting, schema invariants
- integration tests: API + DB + artifact store
- e2e tests: full research cycle with controlled deterministic fixtures

### Evidence artifacts produced automatically
For each phase completion:
- phase gate bundle artifact:
  - test logs
  - coverage report
  - replay digest (if applicable)
  - artifact integrity report
  - invariant report
- stored in artifact store and referenced in DB

Success criteria:
- Every phase has a deterministic e2e or integration evidence artifact.
- Final system completion includes a full run bundle with:
  - trace
  - gate bundle
  - strategy manifest used
  - incident log (should be empty in happy path)
  - integrity report

---

## Operational model
- Local dev: docker-compose for Postgres, Redis, API, worker, UI
- Production: API and worker scale separately, artifact store externalized
- No background writing unless a run is started explicitly
- No “auto-evolve always on” mode. Evolution is a run type with explicit approvals.

---

## Example run configuration (snippet, not code)
This is an example shape, not a stub. Your implementation must validate it strictly.

run:
  seed: 13371337
  budgets:
    max_steps: 240
    max_tool_calls: 500
    max_belief_writes: 200
  gates:
    replay_required: true
    integrity_required: true
    invariants_required: true
    regression_required: true
  strategy_set:
    allow_mutation: true
    mutation_bounds: "bounded"
    promotion_requires_gate_pass: true
  corpus:
    pinned_corpus_id: "pinned-v1"
    embedding_model_id: "text-embedding-3-large"
  ui:
    stream_events: true

---

## What “done” looks like
IRONROOT is finished when:
- A full e2e test run produces a complete run bundle.
- The replay check can reproduce the trace digest from the stored run inputs.
- The UI shows gate status and links to the exact gate bundle artifact and hash.
- A forced failure triggers containment, rollback, repair, and a new regression test.
- Strategy evolution can generate variants but cannot promote anything that fails gates.

If you build this to spec, you will have something that most “agent frameworks” do not: a system that punishes wrongness, preserves history, and forces evidence.
