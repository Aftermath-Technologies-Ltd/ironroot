# Author: Bradley R. Kinnard
"""test suite and gate endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class TestSuiteResult(BaseModel):
    """test suite result response."""

    suite_name: str
    status: str
    passed: int
    failed: int
    skipped: int
    coverage: float
    artifact_id: str | None
    run_at: str | None


@router.get("", response_model=list[TestSuiteResult])
async def list_test_suites() -> list[TestSuiteResult]:
    """lists test suites and last results."""
    # todo: query db in phase 4
    return []
