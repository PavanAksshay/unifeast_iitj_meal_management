"""Keep daily meal changes and link collected meals to their token details."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from app.main import Base

revision = "0006_service_presence"
down_revision = "0005_admin_portal_features"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    columns = {name: {column["name"] for column in inspect(connection).get_columns(name)}
               for name in ("meal_tokens", "meal_servings")}
    for name, length in (("reference", 32), ("student_name_snapshot", 160),
                         ("roll_number_snapshot", 64), ("unit_name_snapshot", 160)):
        if name not in columns["meal_tokens"]:
            op.add_column("meal_tokens", sa.Column(name, sa.String(length), nullable=True))
    if "token_id" not in columns["meal_servings"]:
        op.add_column("meal_servings", sa.Column("token_id", sa.String(36), nullable=True))
    Base.metadata.create_all(bind=connection, tables=[Base.metadata.tables["meal_service_overrides"], Base.metadata.tables["meal_schedule_revisions"]])


def downgrade():
    raise RuntimeError("Meal service and presence records are retained; do not downgrade")
