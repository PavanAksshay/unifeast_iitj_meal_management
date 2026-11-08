"""Create isolated IIT Jodhpur pilot schema.

Revision ID: 0001_initial_schema
Revises:
"""
from alembic import op
from app.main import Base

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.create_all(bind=op.get_bind())


def downgrade():
    raise RuntimeError("Initial schema downgrade is intentionally disabled to preserve pilot history")
