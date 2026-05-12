# Author: Bradley R. Kinnard
"""api_tokens table for /api/v1 authn/authz (Phase 3.4).

Adds an ``api_tokens`` table that stores hashed bearer tokens with
scopes. Tokens are issued opaquely (a random secret returned once at
creation) and stored as a ``sha256`` hash so a DB leak does not expose
the bearer credential. Each token row also carries the human-readable
name the operator gave it, the scopes it grants (``read``, ``write``,
``admin``), creation/last-used timestamps, and an optional revocation
timestamp.

Lookup is by ``token_hash`` (UNIQUE, indexed); the auth dependency
computes ``sha256(presented_token)`` and SELECTs by hash, so neither
the presented token nor any timing-sensitive comparison touches the
DB layer.

Revision ID: 005
Revises: 004
Create Date: 2026-05-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SCOPES_TYPE = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("scopes", _SCOPES_TYPE, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_api_tokens_token_hash"),
    )
    op.create_index("ix_api_tokens_token_hash", "api_tokens", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_api_tokens_token_hash", table_name="api_tokens")
    op.drop_table("api_tokens")
