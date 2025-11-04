"""
SQLAlchemy ORM models.

Defines a minimal 'items' table to replace the prior MongoDB-backed generic collection usage:
- id: UUID primary key
- data: JSONB payload
- created_at: server timestamp default
- updated_at: server timestamp updated on change
"""

from sqlalchemy import Column, text
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP
from sqlalchemy.sql import func

from ..db.sqlalchemy import Base


class Item(Base):
    """ORM model representing a generic item with arbitrary JSON payload."""
    __tablename__ = "items"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    data = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        server_onupdate=func.now(),
    )
