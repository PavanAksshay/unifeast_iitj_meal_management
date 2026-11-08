"""Allow salted password hash encoding.

Revision ID: 0002_widen_password_hash
Revises: 0001_initial_schema
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_widen_password_hash"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("students", "password_hash", type_=sa.String(length=128), existing_type=sa.String(length=64), existing_nullable=False)


def downgrade():
    raise RuntimeError("Password hashes cannot be safely truncated")
