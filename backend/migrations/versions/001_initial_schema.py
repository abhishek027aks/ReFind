"""Create ReFind relational schema.

Revision ID: 001_initial_schema
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("email", sa.String(160), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="student"),
        sa.Column("created_at", sa.String(64), nullable=False),
        sa.CheckConstraint("role IN ('student', 'admin')", name="ck_users_role"),
    )
    op.create_table(
        "reports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("category", sa.String(60), nullable=False),
        sa.Column("location", sa.String(150), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("photo_url", sa.String(300)),
        sa.Column("status", sa.String(30), nullable=False, server_default="open"),
        sa.Column("created_at", sa.String(64), nullable=False),
        sa.CheckConstraint("kind IN ('lost', 'found')", name="ck_reports_kind"),
    )
    op.create_table(
        "claims",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("report_id", sa.Integer, sa.ForeignKey("reports.id"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("ownership_detail", sa.String(1000), nullable=False),
        sa.Column("return_point", sa.String(150), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.String(64), nullable=False),
    )
    op.create_table(
        "matches",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("lost_report_id", sa.Integer, sa.ForeignKey("reports.id"), nullable=False),
        sa.Column("found_report_id", sa.Integer, sa.ForeignKey("reports.id"), nullable=False),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("created_at", sa.String(64), nullable=False),
        sa.UniqueConstraint("lost_report_id", "found_report_id", name="uq_matches_pair"),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("message", sa.String(1000), nullable=False),
        sa.Column("report_id", sa.Integer, sa.ForeignKey("reports.id")),
        sa.Column("read", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.String(64), nullable=False),
    )
    op.create_index("idx_reports_kind_status_created", "reports", ["kind", "status", "created_at"])
    op.create_index("idx_reports_user_id_created", "reports", ["user_id", "created_at"])
    op.create_index("idx_claims_report_id_status", "claims", ["report_id", "status"])
    op.create_index("idx_claims_user_id_status", "claims", ["user_id", "status"])
    op.create_index("idx_notifications_user_id", "notifications", ["user_id", "read", "created_at"])

def downgrade():
    op.drop_index("idx_notifications_user_id", table_name="notifications")
    op.drop_index("idx_claims_user_id_status", table_name="claims")
    op.drop_index("idx_claims_report_id_status", table_name="claims")
    op.drop_index("idx_reports_user_id_created", table_name="reports")
    op.drop_index("idx_reports_kind_status_created", table_name="reports")
    op.drop_table("notifications")
    op.drop_table("matches")
    op.drop_table("claims")
    op.drop_table("reports")
    op.drop_table("users")
