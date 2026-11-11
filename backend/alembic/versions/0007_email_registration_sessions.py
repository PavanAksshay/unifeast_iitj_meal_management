"""Separate email verification/password setup and persist browser sessions."""
from alembic import op
import sqlalchemy as sa

revision = "0007_email_registration_sessions"
down_revision = "0006_service_presence"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    columns = {column["name"] for column in sa.inspect(connection).get_columns("student_otp_challenges")}
    if "requested_at" not in columns:
        op.add_column("student_otp_challenges", sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    if "setup_token_hash" not in columns:
        op.add_column("student_otp_challenges", sa.Column("setup_token_hash", sa.String(64), nullable=True))
        op.create_unique_constraint("uq_otp_setup_token", "student_otp_challenges", ["setup_token_hash"])
    op.execute(sa.text("UPDATE student_otp_challenges SET used_at = CURRENT_TIMESTAMP, setup_token_hash = NULL"))
    if "remembered_sessions" not in sa.inspect(connection).get_table_names():
        op.create_table("remembered_sessions",
                        sa.Column("token_hash", sa.String(64), primary_key=True),
                        sa.Column("subject_id", sa.String(36), nullable=False),
                        sa.Column("kind", sa.String(12), nullable=False),
                        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
        op.create_index("ix_remembered_sessions_subject_id", "remembered_sessions", ["subject_id"])
        op.create_index("ix_remembered_sessions_expires_at", "remembered_sessions", ["expires_at"])


def downgrade():
    raise RuntimeError("Registration and remembered sessions are retained; do not downgrade")
