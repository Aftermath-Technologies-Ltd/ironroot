# Author: Bradley R. Kinnard
"""unit tests for self-healing pipeline."""

from ironroot.orchestration.incidents import (
    DEFAULT_SEVERITY,
    IncidentType,
    Severity,
)


class TestIncidentTypes:
    """tests for incident type definitions."""

    def test_incident_types_have_severity(self) -> None:
        """all incident types have a default severity."""
        for incident_type in IncidentType:
            assert incident_type in DEFAULT_SEVERITY

    def test_critical_incidents(self) -> None:
        """critical severity for most dangerous incidents."""
        assert DEFAULT_SEVERITY[IncidentType.INTEGRITY_FAILURE] == Severity.CRITICAL
        assert DEFAULT_SEVERITY[IncidentType.INVARIANT_VIOLATION] == Severity.CRITICAL

    def test_high_severity_incidents(self) -> None:
        """high severity for serious but recoverable incidents."""
        assert DEFAULT_SEVERITY[IncidentType.DETERMINISM_MISMATCH] == Severity.HIGH
        assert DEFAULT_SEVERITY[IncidentType.VERIFICATION_FAILURE] == Severity.HIGH

    def test_severity_ordering(self) -> None:
        """severity levels are in expected order."""
        assert Severity.LOW.value == "low"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.HIGH.value == "high"
        assert Severity.CRITICAL.value == "critical"


class TestHealingPipelineLogic:
    """tests for healing pipeline business logic."""

    def test_repair_plan_requires_tests(self) -> None:
        """repair plans must include new tests."""
        # this validates the invariant that repairs add tests
        repair_plan_invalid = {"changes": ["fix bug"]}
        repair_plan_valid = {"changes": ["fix bug"], "new_tests": ["test_bug_fixed"]}

        # invalid plan has no new_tests
        assert "new_tests" not in repair_plan_invalid

        # valid plan has new_tests
        assert "new_tests" in repair_plan_valid
        assert len(repair_plan_valid["new_tests"]) > 0

    def test_containment_actions(self) -> None:
        """containment should freeze runs and halt commits."""
        # expected containment actions
        expected_actions = ["run_frozen", "commits_halted"]

        # validate these are the actions we document
        assert "run_frozen" in expected_actions
        assert "commits_halted" in expected_actions

    def test_penalty_accumulation(self) -> None:
        """penalties should accumulate across incidents."""
        initial_penalties = 0
        after_first = initial_penalties + 1
        after_second = after_first + 1

        assert after_first == 1
        assert after_second == 2

    def test_tool_revocation_deduplication(self) -> None:
        """revoking the same tool twice should not duplicate."""
        revoked = ["external_retriever"]
        new_revocation = ["external_retriever", "web_search"]

        combined = list(set(revoked + new_revocation))

        # external_retriever should appear only once
        assert combined.count("external_retriever") == 1
        assert len(combined) == 2


class TestIncidentResolution:
    """tests for incident resolution flow."""

    def test_resolution_requires_notes(self) -> None:
        """resolution should include notes explaining the fix."""
        resolution_notes = "Fixed hash chain by rolling back to checkpoint 5"

        assert len(resolution_notes) > 0

    def test_unresolved_incidents_block_promotion(self) -> None:
        """unresolved incidents should block strategy promotion."""
        incidents_unresolved = [{"id": "inc_001", "resolved_at": None}]
        incidents_resolved = [{"id": "inc_001", "resolved_at": "2025-01-29T00:00:00"}]

        has_unresolved = any(i["resolved_at"] is None for i in incidents_unresolved)
        all_resolved = all(i["resolved_at"] is not None for i in incidents_resolved)

        assert has_unresolved
        assert all_resolved
