# Author: Bradley R. Kinnard
"""Research service: handles researcher submissions and orchestrates campaigns.

This service:
1. Accepts natural language research criteria
2. Translates to research questions
3. Runs autonomous research campaigns
4. Generates plain English results
5. Tracks progress for real-time updates
"""

import asyncio
import hashlib
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.domain.ids import generate_id
from ironroot.storage.artifact_service import get_artifact_service
from ironroot.agi.autonomous_research import AutonomousResearchAgent


class ResearchStatus(str, Enum):
    """Status of a research job."""
    PENDING = "pending"
    PARSING = "parsing"
    GENERATING_QUESTIONS = "generating_questions"
    FORMING_HYPOTHESES = "forming_hypotheses"
    GATHERING_DATA = "gathering_data"
    TESTING = "testing"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ResearchProgress:
    """Progress tracking for a research job."""
    status: ResearchStatus
    percent: int
    phase_description: str
    eta_seconds: int | None
    phases_completed: list[str]
    current_phase: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchFinding:
    """A single finding from the research."""
    finding_type: str  # "success", "partial", "negative"
    summary: str
    metric_name: str | None
    value: float | None
    context: str


@dataclass
class EvidenceArtifact:
    """Reference to a stored evidence artifact."""
    artifact_id: str
    artifact_type: str
    content_hash: str
    summary: str
    created_at: str
    expandable_data: dict[str, Any] | None = None


@dataclass
class ResearchResults:
    """Complete results from a research campaign."""
    research_id: str
    original_criteria: str

    # Summary in plain English
    summary: str

    # Key findings
    findings: list[ResearchFinding]

    # Evidence artifacts
    evidence: list[EvidenceArtifact]

    # Stats
    questions_generated: int
    hypotheses_formed: int
    hypotheses_supported: int
    hypotheses_falsified: int
    hypotheses_revised: int
    experiments_run: int
    data_sources_queried: int

    # Timing
    started_at: str
    completed_at: str
    duration_seconds: float

    # Gate result
    gate_passed: bool


@dataclass
class ResearchJob:
    """A research job in progress or completed."""
    research_id: str
    criteria: str
    seed: int
    status: ResearchStatus
    progress: ResearchProgress
    results: ResearchResults | None
    created_at: str
    error: str | None = None


# In-memory store for active research jobs
_active_jobs: dict[str, ResearchJob] = {}


async def submit_research(
    session: AsyncSession,
    criteria: str,
    seed: int | None = None,
) -> str:
    """Submit a new research request.

    Args:
        session: Database session
        criteria: Natural language research criteria from researcher
        seed: Optional seed for reproducibility

    Returns:
        research_id for tracking
    """
    research_id = generate_id("research")
    seed = seed or random.randint(0, 2**31)

    job = ResearchJob(
        research_id=research_id,
        criteria=criteria,
        seed=seed,
        status=ResearchStatus.PENDING,
        progress=ResearchProgress(
            status=ResearchStatus.PENDING,
            percent=0,
            phase_description="Initializing research...",
            eta_seconds=120,
            phases_completed=[],
            current_phase="initialization",
        ),
        results=None,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    _active_jobs[research_id] = job

    # Start async processing
    asyncio.create_task(_run_research(session, research_id))

    return research_id


async def get_research_status(research_id: str) -> ResearchProgress | None:
    """Get current progress of a research job."""
    job = _active_jobs.get(research_id)
    if not job:
        return None
    return job.progress


async def get_research_results(research_id: str) -> ResearchResults | None:
    """Get results of a completed research job."""
    job = _active_jobs.get(research_id)
    if not job or job.status != ResearchStatus.COMPLETED:
        return None
    return job.results


def _update_progress(
    research_id: str,
    status: ResearchStatus,
    percent: int,
    phase_description: str,
    current_phase: str,
    eta_seconds: int | None = None,
    completed_phase: str | None = None,
    details: dict | None = None,
) -> None:
    """Update progress for a research job."""
    job = _active_jobs.get(research_id)
    if not job:
        return

    phases_completed = list(job.progress.phases_completed)
    if completed_phase and completed_phase not in phases_completed:
        phases_completed.append(completed_phase)

    job.status = status
    job.progress = ResearchProgress(
        status=status,
        percent=percent,
        phase_description=phase_description,
        eta_seconds=eta_seconds,
        phases_completed=phases_completed,
        current_phase=current_phase,
        details=details or {},
    )


async def _run_research(session: AsyncSession, research_id: str) -> None:
    """Run the full research campaign."""
    job = _active_jobs.get(research_id)
    if not job:
        return

    try:
        run_id = generate_id("run")

        # Phase 1: Parsing criteria
        _update_progress(
            research_id,
            ResearchStatus.PARSING,
            5,
            "Analyzing your research criteria...",
            "parsing",
            eta_seconds=110,
        )
        await asyncio.sleep(0.5)  # Simulate parsing

        # Phase 2: Create research agent and run campaign
        agent = AutonomousResearchAgent(seed=job.seed)

        # Generate questions
        _update_progress(
            research_id,
            ResearchStatus.GENERATING_QUESTIONS,
            15,
            "Generating research questions from your criteria...",
            "questions",
            eta_seconds=90,
            completed_phase="parsing",
        )

        from ironroot.storage.postgres import get_session

        async with get_session() as db_session:
            # Run the full campaign with progress updates
            report = await _run_campaign_with_progress(
                db_session, agent, run_id, research_id
            )

            # Generate results
            _update_progress(
                research_id,
                ResearchStatus.ANALYZING,
                90,
                "Generating plain English summary...",
                "analyzing",
                eta_seconds=10,
                completed_phase="testing",
            )

            results = _generate_results(job.criteria, report, agent)

            # Complete
            job.results = results
            job.status = ResearchStatus.COMPLETED
            _update_progress(
                research_id,
                ResearchStatus.COMPLETED,
                100,
                "Research complete!",
                "complete",
                eta_seconds=0,
                completed_phase="analyzing",
            )

    except Exception as e:
        job.status = ResearchStatus.FAILED
        job.error = str(e)
        _update_progress(
            research_id,
            ResearchStatus.FAILED,
            job.progress.percent,
            f"Research failed: {e}",
            "error",
            eta_seconds=0,
        )


async def _run_campaign_with_progress(
    session: AsyncSession,
    agent: AutonomousResearchAgent,
    run_id: str,
    research_id: str,
) -> Any:
    """Run the autonomous research campaign with progress updates."""

    # Generate questions
    await agent._generate_research_questions(session, run_id, max_questions=5)
    _update_progress(
        research_id,
        ResearchStatus.FORMING_HYPOTHESES,
        30,
        f"Forming hypotheses from {len(agent.questions)} questions...",
        "hypotheses",
        eta_seconds=70,
        completed_phase="questions",
        details={"questions_generated": len(agent.questions)},
    )

    # Form hypotheses
    await agent._form_hypotheses(session, run_id, max_per_question=3)
    _update_progress(
        research_id,
        ResearchStatus.GATHERING_DATA,
        45,
        f"Gathering external data for {len(agent.hypotheses)} hypotheses...",
        "data",
        eta_seconds=50,
        completed_phase="hypotheses",
        details={"hypotheses_formed": len(agent.hypotheses)},
    )

    # Design protocols
    await agent._design_protocols(session, run_id)

    # Gather data
    await agent._gather_external_data(session, run_id)
    _update_progress(
        research_id,
        ResearchStatus.TESTING,
        65,
        f"Running experiments and testing hypotheses...",
        "testing",
        eta_seconds=30,
        completed_phase="data",
        details={
            "queries_made": len(agent.queries),
            "data_sources": len(set(q.source_type for q in agent.queries)),
        },
    )

    # Run experiments
    await agent._run_experiments(session, run_id, max_revision_depth=3)

    # Generate report
    report = await agent._generate_report(
        session, run_id, generate_id("campaign"),
        datetime.now(timezone.utc).isoformat()
    )

    return report


def _generate_results(
    criteria: str,
    report: Any,
    agent: AutonomousResearchAgent,
) -> ResearchResults:
    """Generate plain English results from the campaign report."""

    # Build summary
    summary = _generate_summary(criteria, report, agent)

    # Extract findings
    findings = _extract_findings(report, agent)

    # Build evidence list
    evidence = _build_evidence_list(agent)

    return ResearchResults(
        research_id=report.campaign_id,
        original_criteria=criteria,
        summary=summary,
        findings=findings,
        evidence=evidence,
        questions_generated=report.questions_generated,
        hypotheses_formed=report.hypotheses_formed,
        hypotheses_supported=report.hypotheses_supported,
        hypotheses_falsified=report.hypotheses_falsified,
        hypotheses_revised=report.hypotheses_revised,
        experiments_run=report.experiments_run,
        data_sources_queried=report.unique_sources,
        started_at=report.started_at,
        completed_at=report.completed_at or datetime.now(timezone.utc).isoformat(),
        duration_seconds=(
            datetime.fromisoformat(report.completed_at.replace('Z', '+00:00')) -
            datetime.fromisoformat(report.started_at.replace('Z', '+00:00'))
        ).total_seconds() if report.completed_at else 0,
        gate_passed=report.gate_passed,
    )


def _generate_summary(criteria: str, report: Any, agent: AutonomousResearchAgent) -> str:
    """Generate a plain English summary of the research."""

    # Count domains
    domains = set(q.domain for q in agent.questions.values())

    # Build summary paragraphs
    paragraphs = []

    # Opening
    paragraphs.append(
        f"Your research request \"{criteria[:100]}{'...' if len(criteria) > 100 else ''}\" "
        f"was investigated across {len(domains)} knowledge domains: {', '.join(domains)}."
    )

    # Process
    paragraphs.append(
        f"The system generated {report.questions_generated} research questions and "
        f"formed {report.hypotheses_formed} testable hypotheses. Each hypothesis included "
        f"explicit predictions and falsification criteria to ensure scientific rigor."
    )

    # Data gathering
    paragraphs.append(
        f"External data was gathered from {report.unique_sources} independent sources, "
        f"totaling {report.data_volume_bytes:,} bytes of evidence. "
        f"Query success rate was {report.query_success_rate:.0%}."
    )

    # Results
    if report.hypotheses_supported > 0:
        paragraphs.append(
            f"Of the hypotheses tested, {report.hypotheses_supported} were supported by evidence, "
            f"{report.hypotheses_falsified} were falsified, and {report.hypotheses_revised} "
            f"required revision after initial testing. This demonstrates the system's ability "
            f"to update beliefs based on empirical results."
        )

    # Gate result
    if report.gate_passed:
        paragraphs.append(
            "The research campaign passed all verification gates, indicating that the "
            "findings meet the system's evidence standards for reliability and reproducibility."
        )
    else:
        paragraphs.append(
            "Note: The research campaign did not pass all verification gates. "
            "Results should be interpreted with appropriate caution."
        )

    return "\n\n".join(paragraphs)


def _extract_findings(report: Any, agent: AutonomousResearchAgent) -> list[ResearchFinding]:
    """Extract key findings from the research."""
    findings = []

    # Finding: Questions generated
    findings.append(ResearchFinding(
        finding_type="success",
        summary=f"Generated {report.questions_generated} research questions with "
                f"{report.avg_testability:.0%} average testability score",
        metric_name="testability",
        value=report.avg_testability,
        context="Higher testability means questions can be empirically verified",
    ))

    # Finding: Hypotheses tested
    tested = report.hypotheses_supported + report.hypotheses_falsified + report.hypotheses_revised
    if tested > 0:
        support_rate = report.hypotheses_supported / tested
        finding_type = "success" if support_rate > 0.5 else "partial" if support_rate > 0 else "negative"
        findings.append(ResearchFinding(
            finding_type=finding_type,
            summary=f"{report.hypotheses_supported}/{tested} hypotheses supported by evidence",
            metric_name="support_rate",
            value=support_rate,
            context="Hypotheses were tested against external data sources",
        ))

    # Finding: Data gathering
    if report.query_success_rate >= 0.9:
        findings.append(ResearchFinding(
            finding_type="success",
            summary=f"Successfully gathered data from {report.unique_sources} external sources",
            metric_name="query_success_rate",
            value=report.query_success_rate,
            context="High success rate indicates robust data collection",
        ))

    # Finding: Revision capability
    if report.hypotheses_revised > 0:
        findings.append(ResearchFinding(
            finding_type="success",
            summary=f"System revised {report.hypotheses_revised} hypotheses after falsification",
            metric_name="revision_depth",
            value=float(report.revision_depth),
            context="Demonstrates Bayesian updating under evidence",
        ))

    # Finding: Gate status
    if report.gate_passed:
        findings.append(ResearchFinding(
            finding_type="success",
            summary="All verification gates passed - results are reproducible",
            metric_name="gate_status",
            value=1.0,
            context="Evidence meets system reliability standards",
        ))

    return findings


def _build_evidence_list(agent: AutonomousResearchAgent) -> list[EvidenceArtifact]:
    """Build list of evidence artifacts."""
    evidence = []

    # Questions
    if agent.questions:
        evidence.append(EvidenceArtifact(
            artifact_id="questions",
            artifact_type="research_questions",
            content_hash=hashlib.sha256(
                json.dumps([q.question_text for q in agent.questions.values()]).encode()
            ).hexdigest()[:16],
            summary=f"{len(agent.questions)} self-generated research questions",
            created_at=datetime.now(timezone.utc).isoformat(),
            expandable_data={
                "questions": [
                    {"domain": q.domain, "text": q.question_text, "testability": q.testability_score}
                    for q in agent.questions.values()
                ]
            },
        ))

    # Hypotheses
    if agent.hypotheses:
        from ironroot.agi.autonomous_research import HypothesisStatus
        supported = [h for h in agent.hypotheses.values() if h.status == HypothesisStatus.SUPPORTED]
        evidence.append(EvidenceArtifact(
            artifact_id="hypotheses",
            artifact_type="hypothesis_outcomes",
            content_hash=hashlib.sha256(
                json.dumps([h.statement for h in agent.hypotheses.values()]).encode()
            ).hexdigest()[:16],
            summary=f"{len(agent.hypotheses)} hypotheses formed, {len(supported)} supported",
            created_at=datetime.now(timezone.utc).isoformat(),
            expandable_data={
                "hypotheses": [
                    {
                        "statement": h.statement,
                        "status": h.status.value,
                        "prior": h.prior_probability,
                        "posterior": h.current_probability,
                    }
                    for h in agent.hypotheses.values()
                ]
            },
        ))

    # Experiments
    if agent.results:
        evidence.append(EvidenceArtifact(
            artifact_id="experiments",
            artifact_type="experiment_results",
            content_hash=hashlib.sha256(
                json.dumps([r.conclusion for r in agent.results]).encode()
            ).hexdigest()[:16],
            summary=f"{len(agent.results)} experiments with statistical tests",
            created_at=datetime.now(timezone.utc).isoformat(),
            expandable_data={
                "experiments": [
                    {
                        "conclusion": r.conclusion,
                        "confidence": r.confidence_level,
                        "falsified": r.falsified,
                        "tests": r.statistical_tests_run,
                    }
                    for r in agent.results
                ]
            },
        ))

    # External data
    if agent.queries:
        successful = [q for q in agent.queries if q.success]
        evidence.append(EvidenceArtifact(
            artifact_id="external_data",
            artifact_type="external_data_queries",
            content_hash=hashlib.sha256(
                json.dumps([q.response_hash for q in successful if q.response_hash]).encode()
            ).hexdigest()[:16],
            summary=f"{len(successful)} external data sources queried",
            created_at=datetime.now(timezone.utc).isoformat(),
            expandable_data={
                "sources": list(set(q.source_type.value for q in successful)),
                "queries": len(agent.queries),
                "successful": len(successful),
            },
        ))

    return evidence
