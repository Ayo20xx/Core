from datetime import UTC, datetime
import uuid as uuid_mod
from uuid import UUID

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _gen_id() -> str:
    return str(uuid_mod.uuid4())


class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_gen_id
    )
    code: Mapped[str] = mapped_column(String(6), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(default=0)

    def is_valid(self) -> bool:
        return (
            self.used_at is None
            and datetime.now(UTC) < self.expires_at
            and self.attempts < 5
        )