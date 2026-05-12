# Author: Bradley R. Kinnard
"""beliefs.seq monotonic ordering column (Phase 1.1).

Adds the per-chain monotonic ordering used by Phase 1.2's parent lookup.

Revision ID: 002
Revises: 001
Create Date: 2026-05-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """add seq column, backfill, then enforce NOT NULL / UNIQUE / CHECK."""
    # 1. Add column as nullable so we can backfill existing rows.
    op.add_column("beliefs", sa.Column("seq", sa.BigInteger(), nullable=True))

    # 2. Backfill: assign seq per (run_id) ordered by (created_at, id).
    #    `id` is a tiebreaker for any rows with identical timestamps. This is
    #    the documented caveat (upgrade-plan §Risks): if a live install has
    #    truly ambiguous ordering, run the chain_repair audit afterwards.
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY run_id
                        ORDER BY created_at ASC, id ASC
                    ) AS new_seq
                FROM beliefs
            )
            UPDATE beliefs
            SET seq = ranked.new_seq
            FROM ranked
            WHERE beliefs.id = ranked.id
            """
        )
    )

    # 3. Enforce NOT NULL, the per-chain unique constraint, and the
    #    root-iff-seq-one check.
    op.alter_column("beliefs", "seq", nullable=False)
    op.create_unique_constraint("uq_beliefs_run_seq", "beliefs", ["run_id", "seq"])
    op.create_index("ix_beliefs_run_seq", "beliefs", ["run_id", "seq"])
    op.create_check_constraint(
        "ck_beliefs_root_iff_seq_one",
        "beliefs",
        "(parent_hash IS NULL AND seq = 1) OR (parent_hash IS NOT NULL AND seq > 1)",
    )


def downgrade() -> None:
    """drop seq column and its constraints."""
    op.drop_constraint("ck_beliefs_root_iff_seq_one", "beliefs", type_="check")
    op.drop_index("ix_beliefs_run_seq", table_name="beliefs")
    op.drop_constraint("uq_beliefs_run_seq", "beliefs", type_="unique")
    op.drop_column("beliefs", "seq")
