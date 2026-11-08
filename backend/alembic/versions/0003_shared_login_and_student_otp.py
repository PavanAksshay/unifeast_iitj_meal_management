"""Add staff sign-in and student OTP password setup."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from app.main import Base

revision = "0003_shared_login_otp"
down_revision = "0002_widen_password_hash"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    tables = set(inspect(connection).get_table_names())
    if "password_initialized" not in {column["name"] for column in inspect(connection).get_columns("students")}:
        op.add_column("students", sa.Column("password_initialized", sa.Boolean(), nullable=False, server_default=sa.false()))
    missing = [Base.metadata.tables[name] for name in ("staff_users", "student_otp_challenges") if name not in tables]
    if missing:
        Base.metadata.create_all(bind=connection, tables=missing)


def downgrade():
    raise RuntimeError("Identity setup history is retained; do not downgrade this standalone pilot database")
