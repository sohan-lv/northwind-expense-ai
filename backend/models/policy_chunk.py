import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class PolicyChunk(Base):
    __tablename__ = "policy_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_id: Mapped[str] = mapped_column(String, nullable=False)
    doc_title: Mapped[str | None] = mapped_column(String, nullable=True)
    section_number: Mapped[str | None] = mapped_column(String, nullable=True)
    section_title: Mapped[str | None] = mapped_column(String, nullable=True)
    policy_category: Mapped[str | None] = mapped_column(String, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    cross_refs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    is_table: Mapped[bool] = mapped_column(Boolean, default=False)
    is_noise: Mapped[bool] = mapped_column(Boolean, default=False)
    embedding = mapped_column(Vector(1536), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
