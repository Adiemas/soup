"""Initial schema — prompts + prompt_versions + FTS GIN index.

Authored by ``sql-specialist`` under /implement wave 1 to make
``tests/unit/test_migration_0001_schema.py`` pass.

Per ``rules/postgres/migrations.md``:
- Forward + down sections both implemented (§2).
- No runtime DDL (§3): app code never creates these tables.
- GIN index uses ``postgresql_concurrently=False`` here because we are
  inside the initial migration transaction; production non-initial index
  additions will use CONCURRENTLY + ``transactional_ddl = False``.
- Expand/contract not relevant for the initial create.

Revision: 0001
Down-revision: None
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create prompts + prompt_versions tables and the FTS GIN index."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "prompts",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "tags",
            sa.dialects.postgresql.ARRAY(sa.String(length=40)),
            nullable=False,
            server_default=sa.text("ARRAY[]::varchar[]"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "prompt_versions",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "prompt_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prompts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "tags",
            sa.dialects.postgresql.ARRAY(sa.String(length=40)),
            nullable=False,
            server_default=sa.text("ARRAY[]::varchar[]"),
        ),
        sa.Column(
            "approved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("approver", sa.String(length=200), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("author", sa.String(length=200), nullable=False),
        sa.UniqueConstraint(
            "prompt_id", "version", name="ux_prompt_versions_prompt_id_version"
        ),
    )

    # FTS GIN index — `idx_prompts_fts_gin` — REQ-3 (<200ms search on 10k rows).
    op.execute(
        "CREATE INDEX idx_prompts_fts_gin ON prompts "
        "USING GIN (to_tsvector('english', coalesce(title, '') "
        "|| ' ' || coalesce(body, '')))"
    )
    op.create_index(
        "idx_prompts_deleted_at",
        "prompts",
        ["deleted_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    """Drop everything created in ``upgrade`` in reverse order."""
    op.drop_index("idx_prompts_deleted_at", table_name="prompts")
    op.execute("DROP INDEX IF EXISTS idx_prompts_fts_gin")
    op.drop_table("prompt_versions")
    op.drop_table("prompts")
