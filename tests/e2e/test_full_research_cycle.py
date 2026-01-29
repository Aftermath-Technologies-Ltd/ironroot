# Author: Bradley R. Kinnard
"""end-to-end test for full research cycle."""

import tempfile
from pathlib import Path

from ironroot.cognition.memory.append_only_store import AppendOnlyBeliefStore
from ironroot.domain.ids import hash_content
from ironroot.orchestration.lifecycle import create_run
from ironroot.orchestration.supervisor import RunPhase
from ironroot.storage.artifacts import ArtifactStore
from ironroot.verification.integrity import verify_artifact_integrity, verify_belief_chain
from ironroot.verification.regression_gate import execute_gate_suite
from ironroot.verification.replay import compute_replay_digest


class TestFullResearchCycle:
    """e2e test simulating a complete run cycle."""

    def test_deterministic_run_produces_bundle(self) -> None:
        """a fixed-seed run produces verifiable artifacts and passes gates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_store = ArtifactStore(Path(tmpdir))
            belief_store = AppendOnlyBeliefStore()

            # create run with fixed seed
            record, supervisor, budget = create_run(
                seed=42,
                max_steps=100,
                max_tool_calls=50,
                max_belief_writes=20,
            )

            # simulate phases
            supervisor.transition_to(RunPhase.PROPOSE)
            budget.use_step()

            # add a belief
            belief_store.append(
                content=b"proposal: improve test coverage",
                agent_id="agt_proposer",
                run_id=record.run_id,
                confidence=0.85,
            )
            budget.use_belief_write()

            supervisor.transition_to(RunPhase.BUILD)
            budget.use_step()

            # store an artifact
            artifact_data = b"implementation code here"
            artifact_hash = artifact_store.store(artifact_data, artifact_type="code")
            budget.use_tool_call()

            supervisor.transition_to(RunPhase.TEST)
            budget.use_step()

            supervisor.transition_to(RunPhase.VERIFY)
            budget.use_step()

            supervisor.transition_to(RunPhase.AUDIT)
            budget.use_step()

            supervisor.transition_to(RunPhase.DECIDE)
            budget.use_step()

            supervisor.transition_to(RunPhase.FINALIZE)

            # verify integrity
            assert verify_artifact_integrity(artifact_store, artifact_hash)
            assert verify_belief_chain(belief_store)

            # compute replay digest
            trace_events = [b"step1", b"step2", b"step3"]
            belief_chain_hash = hash_content(b"".join(b.content for b in belief_store.list_all()))
            compute_replay_digest(
                run_id=record.run_id,
                seed=42,
                trace_events=trace_events,
                artifact_hashes=[artifact_hash],
                belief_chain_hash=belief_chain_hash,
            )

            # execute gates
            gate_result = execute_gate_suite(
                run_id=record.run_id,
                replay_ok=True,
                integrity_ok=True,
                invariants_ok=True,
                regression_ok=True,
            )

            assert gate_result.overall_status == "passed"
            assert supervisor.is_terminal()
            assert supervisor.phase == RunPhase.FINALIZE

            # budget tracking
            assert budget.steps_used == 6
            assert budget.tool_calls_used == 1
            assert budget.belief_writes_used == 1

    def test_failure_triggers_containment(self) -> None:
        """a failing run is properly stopped."""
        record, supervisor, _budget = create_run(
            seed=999,
            max_steps=10,
            max_tool_calls=5,
            max_belief_writes=3,
        )

        supervisor.transition_to(RunPhase.PROPOSE)

        # simulate a failure
        supervisor.fail("verification found counterexample")

        assert supervisor.is_terminal()
        assert supervisor.phase == RunPhase.FAILED

        # gate should fail
        gate_result = execute_gate_suite(
            run_id=record.run_id,
            replay_ok=False,
            integrity_ok=True,
            invariants_ok=True,
            regression_ok=True,
        )

        assert gate_result.overall_status == "failed"
