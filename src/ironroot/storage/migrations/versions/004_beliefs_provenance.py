# Author: Bradley R. Kinnard
"""beliefs.provenance column + non-empty constraint for derived beliefs (Phase 2c.3).

Adds a structured ``provenance`` JSON column to ``beliefs`` and enforces at
the DB level that derived belief types (hypothesis / prediction / violation /
gate_result / inference) carry a non-empty provenance blob. The
PRIMARY-vs-SECONDARY distinction for observations is enforced in
``BeliefService`` rather than via JSON-path predicates that vary between
PG and SQLite.

Existing rows are backfilled with ``{}`` because (a) lifecycle and
observation rows are legitimately exempt, and (b) at the time this migration
runs no derived rows of the constrained types exist in any deployed DB
(checked via ``EXPERIMENTAL.md`` — none of those types were written by
production code paths before this phase). If a downstream DB violates this
assumption the migration will fail loudly on the CHECK addition.

Revision ID: 004
Revises: 003
Create Date: 2026-05-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROVENANCE_TYPE = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    """add provenance column + CHECK for derived beliefs."""
    op.add_column(
        "beliefs",
        sa.Column(
            "provenance",
            _PROVENANCE_TYPE,
            nullable=False,
            server_default=(
                sa.text("'{}'::jsonb")
                if op.get_bind().dialect.name == "postgresql"
                else sa.text("'{}'")
            ),
        ),
    )
    op.create_check_constraint(
        "ck_beliefs_provenance_for_derived",
        "beliefs",
        "belief_type IN ('lifecycle', 'observation') "
        "OR (provenance IS NOT NULL AND provenance != '{}' AND provenance != '')",
    )


def downgrade() -> None:
    """drop provenance column + its constraint."""
    op.drop_constraint("ck_beliefs_provenance_for_derived", "beliefs", type_="check")
    op.drop_column("beliefs", "provenance")
