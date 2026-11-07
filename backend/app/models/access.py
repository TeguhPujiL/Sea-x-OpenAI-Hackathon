"""Backend-managed case membership. Clients cannot grant themselves access."""
from sqlalchemy import Column, ForeignKey
from app.models.base import Base, UuidV4


class CaseAccess(Base):
    __tablename__ = "case_access"
    case_id = Column(UuidV4, ForeignKey("cases.id"), primary_key=True)
    actor_id = Column(UuidV4, primary_key=True)
