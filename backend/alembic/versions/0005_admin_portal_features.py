"""Add hostel, meal plan, and rebate reporting data for the admin portal."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from app.main import Base

revision = "0005_admin_portal_features"
down_revision = "0004_collection_source"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    columns = {table: {column["name"] for column in inspect(connection).get_columns(table)} for table in ("mess_units", "students", "approved_rebates", "staff_users")}
    additions = {
        "mess_units": [("capacity", sa.Integer(), "0")],
        "students": [("gender", sa.String(24), None), ("hostel", sa.String(120), None), ("bed_type", sa.String(60), None), ("course", sa.String(120), None), ("branch", sa.String(120), None)],
        "approved_rebates": [("reason", sa.String(160), "")],
        "staff_users": [("last_login_at", sa.DateTime(timezone=True), None)],
    }
    for table, fields in additions.items():
        for name, column_type, default in fields:
            if name not in columns[table]:
                kwargs = {"nullable": name not in ("capacity", "reason")}
                if default is not None:
                    kwargs["server_default"] = sa.text(default) if default.isdigit() else default
                op.add_column(table, sa.Column(name, column_type, **kwargs))
    Base.metadata.create_all(bind=connection, tables=[Base.metadata.tables["meal_plans"]])


def downgrade():
    raise RuntimeError("Admin reporting and meal plan data are retained; do not downgrade")
