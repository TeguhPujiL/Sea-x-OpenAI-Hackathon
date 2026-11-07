"""Trusted local operator command to grant case membership; not a public API."""
import argparse
from uuid import UUID, uuid4
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.database import build_engine
from app.core.security import get_actor
from app.core.transactions import audit
from app.models import Case, CaseAccess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True, type=UUID)
    parser.add_argument("--actor-id", required=True, type=UUID)
    args = parser.parse_args()
    if args.case_id.version != 4 or args.actor_id.version != 4:
        parser.error("IDs must be UUID v4")
    settings = get_settings()
    actor = get_actor(settings)
    if actor.role != "ADMIN" or "case:write" not in actor.scopes:
        raise PermissionError("Trusted ADMIN context with case:write is required")
    engine = build_engine(settings.database_url)
    try:
        with Session(engine) as db, db.begin():
            case = db.get(Case, args.case_id)
            if case is None or case.deleted_at:
                raise ValueError("Active case not found")
            if db.get(CaseAccess, (args.case_id, args.actor_id)) is None:
                db.add(CaseAccess(case_id=args.case_id, actor_id=args.actor_id))
                audit(db, actor, f"req_{uuid4().hex}", case.id, "CASE_ACCESS_GRANTED", "case", case.id,
                    case.version, {"granted_actor_id": str(args.actor_id)})
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
