# IMMUTABLE TABLE — INSERT ONLY
# Never expose an update or delete endpoint for this table.
# This is the audit log. Original verdicts must always be preserved.

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class Override(Base):
    __tablename__ = "overrides"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    verdict_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("verdicts.id"), nullable=False)
    original_verdict: Mapped[str] = mapped_column(String, nullable=False)
    new_verdict: Mapped[str] = mapped_column(String, nullable=False)
    reviewer_comment: Mapped[str] = mapped_column(String, nullable=False)
    overridden_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    overridden_by: Mapped[str | None] = mapped_column(String, nullable=True)

    verdict: Mapped["Verdict"] = relationship("Verdict", back_populates="overrides")
