# Author: Bradley R. Kinnard
"""tool access policy enforcement."""

from ironroot.domain.policies import AgentPolicy, ToolPermission


def can_use_tool(policy: AgentPolicy, tool: ToolPermission, revoked: set[ToolPermission]) -> bool:
    """checks if tool is allowed by policy and not revoked."""
    if tool in revoked:
        return False
    return tool in policy.allowed_tools


def list_available_tools(
    policy: AgentPolicy, revoked: set[ToolPermission]
) -> list[ToolPermission]:
    """returns tools available to agent after revocations."""
    return [t for t in policy.allowed_tools if t not in revoked]
