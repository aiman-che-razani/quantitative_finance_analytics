"""Indexes for list/recovery queries and CHECK constraints on experiment status/kind.

Purely additive. Before upgrading a cluster with existing rows, confirm
`SELECT DISTINCT status, kind FROM experiments` only returns the allowed values.
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_datasets_created_at", "datasets", ["created_at"])
    op.create_index("ix_datasets_parent_id", "datasets", ["parent_id"])
    op.create_index("ix_experiments_created_at", "experiments", ["created_at"])
    op.create_index("ix_experiments_status_created_at", "experiments", ["status", "created_at"])
    op.create_index("ix_experiments_dataset_id", "experiments", ["dataset_id"])
    op.create_index("ix_paper_accounts_updated_at", "paper_accounts", ["updated_at"])
    op.create_check_constraint(
        "ck_experiments_status",
        "experiments",
        "status IN ('RUNNING','SUCCEEDED','FAILED','INTERRUPTED')",
    )
    op.create_check_constraint("ck_experiments_kind", "experiments", "kind IN ('backtest','ml')")


def downgrade():
    op.drop_constraint("ck_experiments_kind", "experiments", type_="check")
    op.drop_constraint("ck_experiments_status", "experiments", type_="check")
    op.drop_index("ix_paper_accounts_updated_at", "paper_accounts")
    op.drop_index("ix_experiments_dataset_id", "experiments")
    op.drop_index("ix_experiments_status_created_at", "experiments")
    op.drop_index("ix_experiments_created_at", "experiments")
    op.drop_index("ix_datasets_parent_id", "datasets")
    op.drop_index("ix_datasets_created_at", "datasets")
