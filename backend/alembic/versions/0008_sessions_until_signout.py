"""Keep remembered sessions valid until sign-out."""
from alembic import op
import sqlalchemy as sa

revision = "0008_sessions_until_signout"
down_revision = "0007_email_registration_sessions"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    columns = {column["name"] for column in sa.inspect(connection).get_columns("remembered_sessions")}
    if "expires_at" in columns:
        op.drop_index("ix_remembered_sessions_expires_at", table_name="remembered_sessions")
        op.drop_column("remembered_sessions", "expires_at")


def downgrade():
    raise RuntimeError("Remembered sessions are retained; do not downgrade")
