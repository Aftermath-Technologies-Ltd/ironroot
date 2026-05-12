# Author: Bradley R. Kinnard
"""runs.replay_digest baseline column (Phase 1.5).

Stores the chain digest sealed at run completion. The replay gate
recomputes from live rows and compares.

Revision ID: 003
Revises: 002
Create Date: 2026-05-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """add replay_digest + replay_digest_sealed_at to runs."""
    op.add_column("runs", sa.Column("replay_digest", sa.String(64), nullable=True))
    op.add_column(
        "runs",
        sa.Column("replay_digest_sealed_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    """drop replay digest columns."""
    op.drop_column("runs", "replay_digest_sealed_at")
    op.drop_column("runs", "replay_digest")
