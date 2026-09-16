"""Initial operational metadata schema."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "instruments",
        sa.Column("symbol", sa.String(16), primary_key=True),
        sa.Column("definition", JSONB, nullable=False),
    )
    op.create_table(
        "datasets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("parent_id", sa.String(64), sa.ForeignKey("datasets.id")),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("symbols", JSONB, nullable=False),
        sa.Column("quality", JSONB, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "ingestion_heads",
        sa.Column("stream", sa.String(64), primary_key=True),
        sa.Column("dataset_id", sa.String(64), sa.ForeignKey("datasets.id"), nullable=False),
    )
    op.create_table(
        "experiments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("dataset_id", sa.String(64), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("config", JSONB, nullable=False),
        sa.Column("result", JSONB),
        sa.Column("error", sa.String(1000)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "paper_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("config", JSONB, nullable=False),
        sa.Column("state", JSONB, nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade():
    for name in ["paper_accounts", "experiments", "ingestion_heads", "datasets", "instruments"]:
        op.drop_table(name)
