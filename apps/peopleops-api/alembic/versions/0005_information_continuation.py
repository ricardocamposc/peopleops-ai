"""support durable needs-information continuations"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_information_continuation"
down_revision = "0004_evaluation_trace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_interaction",
        sa.Column("continuation_of_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "analysis_interaction", sa.Column("user_context", postgresql.JSONB(), nullable=True)
    )
    op.create_foreign_key(
        "fk_analysis_interaction_continuation_of",
        "analysis_interaction",
        "analysis_interaction",
        ["continuation_of_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_analysis_interaction_continuation_of", "analysis_interaction", type_="foreignkey"
    )
    op.drop_column("analysis_interaction", "user_context")
    op.drop_column("analysis_interaction", "continuation_of_id")
