"""P1-only append-only tables, deliberately outside P0 Base.metadata."""
from sqlalchemy import Column, ForeignKey, Integer, JSON, String, Date, event
from sqlalchemy.orm import DeclarativeBase, Session
from app.models import Case, AnalysisJob, AiExecution
from app.models.base import Identity, Created, UuidV4


class P1Base(DeclarativeBase):
    pass


class AssessmentCheck(Identity, Created, P1Base):
    __tablename__ = "p1_checks"
    case_id = Column(UuidV4, ForeignKey(Case.id), nullable=False, index=True)
    job_id = Column(UuidV4, ForeignKey(AnalysisJob.id), nullable=False, unique=True)
    kind = Column(String, nullable=False)
    supplier_ref = Column(String)
    version = Column(Integer, nullable=False)
    previous_check_id = Column(UuidV4, ForeignKey("p1_checks.id"))
    reference_date = Column(Date, nullable=False)
    request_json = Column(JSON, nullable=False)
    documents_json = Column(JSON, nullable=False)


class AssessmentResult(Created, P1Base):
    __tablename__ = "p1_check_results"
    check_id = Column(UuidV4, ForeignKey("p1_checks.id"), primary_key=True)
    ai_execution_id = Column(UuidV4, ForeignKey(AiExecution.id), nullable=False, unique=True)
    result_json = Column(JSON, nullable=False)


class P1Revision(P1Base):
    __tablename__ = "p1_schema_revisions"
    revision = Column(String, primary_key=True)


@event.listens_for(Session, "before_flush")
def immutable_assessments(session, _context, _instances):
    for row in list(session.dirty) + list(session.deleted):
        if isinstance(row, (AssessmentCheck, AssessmentResult, P1Revision)) and (
            row in session.deleted or session.is_modified(row)
        ):
            raise ValueError("P1 assessment records are immutable")
