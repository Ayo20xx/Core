"""create verification codes table

Revision ID: 9f8b3c2a1d4e
Revises: 044a1e648a26
Create Date: 2026-11-24 00:00:00.000000

"""
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "9f8b3c2a1d4e"
down_revision = "044a1e648a26"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "verification_codes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(6), nullable=False),
        sa.Column("code_hash", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("email", name="ix_verification_codes_email"),
    )


def downgrade() -> None:
    op.drop_table("verification_codes")