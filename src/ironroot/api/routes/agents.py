# Author: Bradley R. Kinnard
"""agent management endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class AgentResponse(BaseModel):
    """agent details response."""

    agent_id: str
    role: str
    run_id: str
    budget_remaining: dict[str, int]
    penalties: list[dict[str, object]]
    tool_access: list[str]
    status: str


@router.get("", response_model=list[AgentResponse])
async def list_agents(run_id: str | None = None) -> list[AgentResponse]:
    """lists agents with penalties, tool access, survival stats."""
    # todo: query db in phase 3
    return []


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str) -> AgentResponse:
    """returns agent details and incident history."""
    # todo: fetch from db in phase 3
    raise HTTPException(status_code=404, detail=f"agent not found: {agent_id}")
