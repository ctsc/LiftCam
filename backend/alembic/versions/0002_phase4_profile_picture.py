"""Add users.profile_picture_url for signup/profile (Phase 4).

Revision ID: 0002_phase4
Revises: 0001_phase3
Create Date: 2026-09-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_phase4"
down_revision: Union[str, None] = "0001_phase3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEFAULT_PFP = "https://static.liftcam.app/avatars/default.png"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "profile_picture_url",
            sa.String(length=1024),
            nullable=False,
            server_default=_DEFAULT_PFP,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "profile_picture_url")
