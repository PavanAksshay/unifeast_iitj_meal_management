"""Record student slide as meal collection source."""
from alembic import op
from sqlalchemy import inspect

revision = "0004_collection_source"
down_revision = "0003_shared_login_otp"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("meal_servings")}
    if "counter_id" in columns and "collection_source" not in columns:
        op.alter_column("meal_servings", "counter_id", new_column_name="collection_source")


def downgrade():
    raise RuntimeError("Collection source history is retained; do not revert this workflow change")

