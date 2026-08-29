"""persist structured evaluation trace"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_evaluation_trace"
down_revision = "0003_human_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analysis_interaction", sa.Column("evaluation_trace", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("analysis_interaction", "evaluation_trace")
