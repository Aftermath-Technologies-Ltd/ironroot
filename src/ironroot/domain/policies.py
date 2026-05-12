# Author: Bradley R. Kinnard
"""policy definitions for agents and strategies."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal


class ToolPermission(StrEnum):
    """tools an agent may or may not use."""

    RETRIEVER = "retriever"
    CODE_EXEC = "code_exec"
    WEB_FETCH = "web_fetch"
    FILE_WRITE = "file_write"
    BELIEF_WRITE = "belief_write"


@dataclass(frozen=True, slots=True)
class AgentPolicy:
    """immutable policy for a single agent role."""

    role: Literal["proposer", "builder", "tester", "verifier", "auditor", "supervisor", "repair"]
    allowed_tools: frozenset[ToolPermission] = field(default_factory=frozenset)
    max_steps: int = 100
    max_tool_calls: int = 50
    max_belief_writes: int = 20
    can_propose_strategy: bool = False
    can_promote_strategy: bool = False


# default policies per role, can be overridden by strategy manifests
DEFAULT_POLICIES: dict[str, AgentPolicy] = {
    "proposer": AgentPolicy(
        role="proposer",
        allowed_tools=frozenset({ToolPermission.RETRIEVER}),
        can_propose_strategy=True,
    ),
    "builder": AgentPolicy(
        role="builder",
        allowed_tools=frozenset({ToolPermission.CODE_EXEC, ToolPermission.FILE_WRITE}),
    ),
    "tester": AgentPolicy(
        role="tester",
        allowed_tools=frozenset({ToolPermission.CODE_EXEC}),
    ),
    "verifier": AgentPolicy(
        role="verifier",
        allowed_tools=frozenset({ToolPermission.RETRIEVER, ToolPermission.CODE_EXEC}),
    ),
    "auditor": AgentPolicy(
        role="auditor",
        allowed_tools=frozenset({ToolPermission.RETRIEVER}),
    ),
    "supervisor": AgentPolicy(
        role="supervisor",
        allowed_tools=frozenset(),
        can_promote_strategy=True,
    ),
    "repair": AgentPolicy(
        role="repair",
        allowed_tools=frozenset({ToolPermission.CODE_EXEC, ToolPermission.FILE_WRITE}),
    ),
}
