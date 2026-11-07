"""Same-origin demo composition. Owners retain calculation/decision logic."""
import json
import os
from pathlib import Path
from fastapi import Depends, Request
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from app.api.response import ApiError
from app.core.config import ROOT, get_settings
from app.core.integration import AuditCommand
from app.core.security import get_actor
from app.core.transactions import case_for, resource_for
from app.main import create_app
from app.core.login import LoginSettings, install_login
from app.models import CaseAccess, Finding
from app.services.assurance.access import get_case_grants
from app.services.assurance.audit import append_audit


class AssuranceAuditAdapter:
    def record(self, session, command: AuditCommand):
        append_audit(session,actor=command.actor,case_id=command.case_id,request_id=command.request_id,
            event_type=command.event_type,resource_type=command.resource_type,resource_id=command.resource_id,
            resource_version=command.version,details=json.loads(command.details_json))


def create_web_app(settings=None, static_directory=None, login_settings=None):
    config=settings or get_settings()
    app=create_app(config,audit_service=AssuranceAuditAdapter())
    # Explicit local prototype extension; the locked v1.1 contract is unchanged.
    # The feature's separate SQLite migration must be invoked before opt-in.
    if os.environ.get("PROCUREMIND_FINDING_SCENARIOS_ENABLED", "").lower() in {"1", "true", "yes"}:
        if not config.demo_mode:
            raise RuntimeError("Experimental finding scenarios require the explicit demo composition")
        from app.services.assurance.finding_scenarios.router import router as finding_scenarios_router
        app.include_router(finding_scenarios_router, prefix="/api/v1/experimental")

    def persisted_grants(request: Request, actor=Depends(get_actor)):
        with request.app.state.session_factory() as session:
            ids=session.scalars(select(CaseAccess.case_id).where(CaseAccess.actor_id==actor.actor_id)).all()
            return {actor.actor_id:frozenset(ids)}
    app.dependency_overrides[get_case_grants]=persisted_grants

    class DemoSimulationPolicy:
        # Only server-configured demo identity is supported by this composition.
        def require_case(self, case_id):
            actor=get_actor(config)
            with app.state.session_factory() as session: case_for(session,actor,case_id)
        def require_finding(self, case_id, finding_id):
            actor=get_actor(config)
            with app.state.session_factory() as session:
                case_for(session,actor,case_id)
                finding=resource_for(session,actor,Finding,finding_id)
                if finding.case_id!=case_id:
                    raise ApiError(404,'RESOURCE_NOT_FOUND','Finding not found')

    @app.middleware('http')
    async def simulation_policy(request,call_next):
        request.state.simulation_access=DemoSimulationPolicy()
        return await call_next(request)

    install_login(app, login_settings or LoginSettings())

    directory=Path(static_directory) if static_directory else ROOT/'frontend'/'dist'
    if not directory.joinpath('index.html').is_file():
        raise RuntimeError('Frontend build missing: run scripts/demo_runtime.py setup first')
    app.mount('/',StaticFiles(directory=directory,html=True),name='frontend')
    return app
