from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, Integer, JSON, MetaData, String, event
from sqlalchemy.orm import DeclarativeBase, Session

from app.models import AiExecution, AnalysisJob, Case, Finding
from app.models.base import Base, Created, Identity, UuidV4


class FeatureBase(DeclarativeBase):
    # Separate metadata prevents core bootstrap/create_all from adopting an
    # experimental table. Only this feature's explicit migration installs it.
    metadata = MetaData(naming_convention=Base.metadata.naming_convention)


class FindingScenario(Identity, Created, FeatureBase):
    __tablename__ = "finding_scenarios"
    case_id = Column(UuidV4, ForeignKey(Case.__table__.c.id), nullable=False)
    finding_id = Column(UuidV4, ForeignKey(Finding.__table__.c.id), nullable=False)
    analysis_job_id = Column(UuidV4, ForeignKey(AnalysisJob.__table__.c.id), nullable=False)
    ai_execution_id = Column(UuidV4, ForeignKey(AiExecution.__table__.c.id), nullable=False, unique=True)
    actor_id = Column(UuidV4, nullable=False)
    request_id = Column(String, nullable=False)
    source_case_version = Column(Integer, nullable=False)
    source_finding_version = Column(Integer, nullable=False)
    context_sha256 = Column(String(64), nullable=False)
    status = Column(String, nullable=False)
    payload_json = Column(JSON, nullable=False)
    __table_args__ = (
        CheckConstraint("source_case_version >= 1 AND source_finding_version >= 1", name="positive_source_versions"),
        CheckConstraint("status IN ('DRAFT','NEEDS_REVIEW')", name="scenario_status"),
        CheckConstraint("length(context_sha256) = 64", name="context_digest"),
        CheckConstraint("json_valid(payload_json)", name="valid_payload"),
        Index("ix_finding_scenarios_case_created", "case_id", "created_at", "id"),
    )


@event.listens_for(Session, "before_flush")
def immutable_scenarios(session, _context, _instances):
    for row in list(session.deleted) + [value for value in session.dirty if session.is_modified(value)]:
        if isinstance(row, FindingScenario):
            raise ValueError("Finding scenarios are immutable")
