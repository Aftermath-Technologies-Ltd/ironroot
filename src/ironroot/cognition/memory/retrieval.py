# Author: Bradley R. Kinnard
"""belief retrieval utilities."""

from ironroot.cognition.memory.append_only_store import AppendOnlyBeliefStore, BeliefRecord


def retrieve_by_agent(store: AppendOnlyBeliefStore, agent_id: str) -> list[BeliefRecord]:
    """retrieves all beliefs created by an agent."""
    return [b for b in store.list_all() if b.agent_id == agent_id]


def retrieve_by_run(store: AppendOnlyBeliefStore, run_id: str) -> list[BeliefRecord]:
    """retrieves all beliefs from a run."""
    return [b for b in store.list_all() if b.run_id == run_id]


def retrieve_recent(store: AppendOnlyBeliefStore, count: int) -> list[BeliefRecord]:
    """retrieves the most recent beliefs."""
    all_beliefs = store.list_all()
    return all_beliefs[-count:] if len(all_beliefs) >= count else all_beliefs
