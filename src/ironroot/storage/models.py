# Author: Bradley R. Kinnard
"""sqlalchemy models for all database tables."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ironroot.storage.postgres import Base

# Production runs against PostgreSQL (JSONB for indexable JSON columns).
# Integrity tests use aiosqlite, which has no JSONB; the variant falls back
# to the generic SQLAlchemy JSON type there. The migration still emits JSONB
# because Alembic targets the live PG database.
JsonCol = JSONB().with_variant(JSON(), "sqlite")


def _utc_now() -> datetime:
    """Default callable for `mapped_column(default=...)`; returns aware UTC now."""
    return datetime.now(UTC)


class ArtifactRecord(Base):
    """metadata for content-addressed artifacts."""

    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        Index("ix_artifacts_type_created", "artifact_type", "created_at"),
        UniqueConstraint("content_hash", name="uq_artifacts_content_hash"),
    )


class RunRecord(Base):
    """run configuration and status."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    phase: Mapped[str] = mapped_column(String(20), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JsonCol, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # budget tracking
    steps_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_calls_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    belief_writes_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Phase 1.5: replay digest sealed at run completion. The replay gate
    # recomputes the digest from the live chain and compares.
    replay_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    replay_digest_sealed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    beliefs: Mapped[list["BeliefRecord"]] = relationship(back_populates="run")
    agents: Mapped[list["AgentRecord"]] = relationship(back_populates="run")
    incidents: Mapped[list["IncidentRecord"]] = relationship(back_populates="run")
    gates: Mapped[list["GateRecord"]] = relationship(back_populates="run")


class BeliefRecord(Base):
    """append-only belief records with hash chain.

    `seq` is the monotonic per-chain ordering column introduced in Phase 1.1.
    It is unique within `(run_id, seq)` and the row whose `seq = 1` is the
    chain root (has `parent_hash IS NULL`). All chain-parent lookups use
    `ORDER BY seq DESC` with `FOR UPDATE` plus a Postgres advisory lock keyed
    on `run_id`. Do not order by `created_at` for chain logic.
    """

    __tablename__ = "beliefs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("runs.id"), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    belief_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="lifecycle", index=True
    )  # lifecycle, observation, hypothesis, prediction, gate_result, violation
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    parent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content: Mapped[dict[str, Any]] = mapped_column(JsonCol, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JsonCol, nullable=False, default=list)
    topic_tags: Mapped[list[str]] = mapped_column(JsonCol, nullable=False, default=list)
    # Phase 2c.3: structured ProvenanceRef. Mandatory for any non-PRIMARY
    # belief — DB-enforced via ck_beliefs_provenance_for_derived below plus
    # application-level validation in BeliefService. Empty dict = no source
    # (acceptable only for lifecycle events and PRIMARY observations).
    provenance: Mapped[dict[str, Any]] = mapped_column(JsonCol, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utc_now)

    run: Mapped["RunRecord"] = relationship(back_populates="beliefs")
    contradictions: Mapped[list["ContradictionRecord"]] = relationship(
        back_populates="belief", foreign_keys="ContradictionRecord.belief_id"
    )

    __table_args__ = (
        Index("ix_beliefs_run_agent", "run_id", "agent_id"),
        Index("ix_beliefs_run_seq", "run_id", "seq"),
        UniqueConstraint("run_id", "seq", name="uq_beliefs_run_seq"),
        CheckConstraint(
            "(parent_hash IS NULL AND seq = 1) OR (parent_hash IS NOT NULL AND seq > 1)",
            name="ck_beliefs_root_iff_seq_one",
        ),
        # Phase 2c.3: every derived belief must carry a non-empty provenance
        # blob. Lifecycle events and observations are the only types that
        # may legitimately have no upstream belief (lifecycle = bookkeeping;
        # PRIMARY observations sit at the bottom of the inference graph).
        # The PRIMARY-vs-SECONDARY distinction for observations is enforced
        # at the BeliefService layer because metric_class lives inside the
        # JSON content column and writing a portable CHECK over JSON across
        # PG/SQLite is fragile.
        CheckConstraint(
            "belief_type IN ('lifecycle', 'observation') "
            "OR (provenance IS NOT NULL AND provenance != '{}' AND provenance != '')",
            name="ck_beliefs_provenance_for_derived",
        ),
    )


class ContradictionRecord(Base):
    """links between contradicting beliefs."""

    __tablename__ = "contradictions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    belief_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("beliefs.id"), nullable=False, index=True
    )
    contradicts_belief_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("beliefs.id"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utc_now)

    belief: Mapped["BeliefRecord"] = relationship(
        back_populates="contradictions", foreign_keys=[belief_id]
    )
    contradicts: Mapped["BeliefRecord"] = relationship(foreign_keys=[contradicts_belief_id])


class AgentRecord(Base):
    """agent state including budgets and penalties."""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("runs.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    # budgets
    max_steps: Mapped[int] = mapped_column(Integer, nullable=False)
    max_tool_calls: Mapped[int] = mapped_column(Integer, nullable=False)
    steps_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_calls_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # penalties
    penalty_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tools_revoked: Mapped[list[str]] = mapped_column(JsonCol, nullable=False, default=list)
    restricted_tasks: Mapped[list[str]] = mapped_column(JsonCol, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utc_now)
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    run: Mapped["RunRecord"] = relationship(back_populates="agents")


class StrategyRecord(Base):
    """versioned strategy manifests."""

    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JsonCol, nullable=False)

    # status
    gate_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    promoted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # scoring
    correctness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reproducibility_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    efficiency_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    safety_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (UniqueConstraint("name", "version", name="uq_strategies_name_version"),)


class IncidentRecord(Base):
    """failure incidents with evidence."""

    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("runs.id"), nullable=False, index=True
    )
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    incident_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JsonCol, nullable=False, default=list)
    penalties_applied: Mapped[dict[str, Any]] = mapped_column(
        JsonCol, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    run: Mapped["RunRecord"] = relationship(back_populates="incidents")


class ApiTokenRecord(Base):
    """Phase 3.4: opaque bearer tokens with scopes for /api/v1 auth.

    Tokens are stored as ``sha256(secret)`` hashes; the raw secret is
    returned exactly once at creation time. Scopes are a JSON list of
    strings drawn from ``{"read", "write", "admin"}``. ``revoked_at``
    soft-deletes a token without losing the audit trail.
    """

    __tablename__ = "api_tokens"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    scopes: Mapped[list[str]] = mapped_column(JsonCol, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utc_now)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("token_hash", name="uq_api_tokens_token_hash"),)


class GateRecord(Base):
    """gate execution results."""

    __tablename__ = "gates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("runs.id"), nullable=False, index=True
    )
    gate_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    artifact_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    results: Mapped[dict[str, Any]] = mapped_column(JsonCol, nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utc_now)

    run: Mapped["RunRecord"] = relationship(back_populates="gates")
