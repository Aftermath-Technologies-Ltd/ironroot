# Author: Bradley R. Kinnard
"""initial schema with all core tables.

Revision ID: 001
Revises:
Create Date: 2026-01-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """create all tables."""
    # runs table
    op.create_table(
        "runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("seed", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("phase", sa.String(20), nullable=False),
        sa.Column("config", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column("steps_used", sa.Integer, nullable=False, default=0),
        sa.Column("tool_calls_used", sa.Integer, nullable=False, default=0),
        sa.Column("belief_writes_used", sa.Integer, nullable=False, default=0),
    )

    # artifacts table
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("content_hash", sa.String(64), nullable=False, index=True),
        sa.Column("artifact_type", sa.String(50), nullable=False, index=True),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False, index=True),
        sa.Column("run_id", sa.String(64), nullable=True, index=True),
        sa.Column("filename", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("content_hash", name="uq_artifacts_content_hash"),
    )
    op.create_index(
        "ix_artifacts_type_created", "artifacts", ["artifact_type", "created_at"]
    )

    # beliefs table
    op.create_table(
        "beliefs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "run_id", sa.String(64), sa.ForeignKey("runs.id"), nullable=False, index=True
        ),
        sa.Column("agent_id", sa.String(64), nullable=False, index=True),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("parent_hash", sa.String(64), nullable=True),
        sa.Column("content", postgresql.JSONB, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB, nullable=False),
        sa.Column("topic_tags", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_beliefs_run_agent", "beliefs", ["run_id", "agent_id"])

    # contradictions table
    op.create_table(
        "contradictions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "belief_id",
            sa.String(64),
            sa.ForeignKey("beliefs.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "contradicts_belief_id",
            sa.String(64),
            sa.ForeignKey("beliefs.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("detected_at", sa.DateTime, nullable=False),
    )

    # agents table
    op.create_table(
        "agents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "run_id", sa.String(64), sa.ForeignKey("runs.id"), nullable=False, index=True
        ),
        sa.Column("role", sa.String(20), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("max_steps", sa.Integer, nullable=False),
        sa.Column("max_tool_calls", sa.Integer, nullable=False),
        sa.Column("steps_used", sa.Integer, nullable=False, default=0),
        sa.Column("tool_calls_used", sa.Integer, nullable=False, default=0),
        sa.Column("penalty_count", sa.Integer, nullable=False, default=0),
        sa.Column("tools_revoked", postgresql.JSONB, nullable=False),
        sa.Column("restricted_tasks", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("terminated_at", sa.DateTime, nullable=True),
    )

    # strategies table
    op.create_table(
        "strategies",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, index=True),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.Column("manifest", postgresql.JSONB, nullable=False),
        sa.Column("gate_passed", sa.Boolean, nullable=False, default=False),
        sa.Column("promoted", sa.Boolean, nullable=False, default=False),
        sa.Column("promoted_at", sa.DateTime, nullable=True),
        sa.Column("correctness_score", sa.Float, nullable=True),
        sa.Column("reproducibility_score", sa.Float, nullable=True),
        sa.Column("efficiency_score", sa.Float, nullable=True),
        sa.Column("safety_score", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("name", "version", name="uq_strategies_name_version"),
    )

    # incidents table
    op.create_table(
        "incidents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "run_id", sa.String(64), sa.ForeignKey("runs.id"), nullable=False, index=True
        ),
        sa.Column("agent_id", sa.String(64), nullable=True, index=True),
        sa.Column("incident_type", sa.String(50), nullable=False, index=True),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB, nullable=False),
        sa.Column("penalties_applied", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
    )

    # gates table
    op.create_table(
        "gates",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "run_id", sa.String(64), sa.ForeignKey("runs.id"), nullable=False, index=True
        ),
        sa.Column("gate_type", sa.String(50), nullable=False, index=True),
        sa.Column("passed", sa.Boolean, nullable=False),
        sa.Column("artifact_id", sa.String(64), nullable=True),
        sa.Column("results", postgresql.JSONB, nullable=False),
        sa.Column("executed_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    """drop all tables."""
    op.drop_table("gates")
    op.drop_table("incidents")
    op.drop_table("strategies")
    op.drop_table("agents")
    op.drop_table("contradictions")
    op.drop_table("beliefs")
    op.drop_table("artifacts")
    op.drop_table("runs")
