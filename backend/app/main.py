import logging
import traceback
from pathlib import Path
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from app.api.response import ApiError, failure, success
from app.api.routes import router
from app.core.config import Settings, get_settings
from app.core.database import build_engine, session_factory
from app.core.upload_limit import UploadLimitMiddleware
from app.services.ai.provider import OpenAIAnalysisProvider
from app.services.ai.jobs import recover_interrupted_jobs
from app.services.ai.decisions import OpenAIDecisionProvider
from app.core.integration import (CoreAuditAdapter, StoredSimulationLookup, StoredReferenceLookup, SubmittedRepairPreconditions, AuditService, SimulationLookup, ReferenceLookup, ReviewPreconditionValidator)
from app.schemas.shared import Envelope, ErrorDetail, HealthData


def create_app(settings: Settings | None = None, *, simulation_lookup: SimulationLookup | None = None,
    audit_service: AuditService | None = None, reference_lookup: ReferenceLookup | None = None,
    review_preconditions: ReviewPreconditionValidator | None = None) -> FastAPI:
    config = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = build_engine(config.database_url)
        app.state.session_factory = session_factory(engine)
        app.state.session_factory.configure(info={"audit_service_provider": lambda: app.state.audit_service})
        recover_interrupted_jobs(app)
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="ProcureMind V4.1", version="1.1", lifespan=lifespan,
        description="Teguh P0 case/document/analysis/finding/challenge/repair backend. Simulation/review/audit services remain owner-integrated.")
    app.state.settings = config
    app.state.analysis_provider = OpenAIAnalysisProvider(config)
    app.state.decision_provider = OpenAIDecisionProvider(config)
    app.state.audit_service = audit_service or CoreAuditAdapter()
    app.state.simulation_lookup = simulation_lookup or StoredSimulationLookup()
    app.state.reference_lookup = reference_lookup or StoredReferenceLookup()
    app.state.review_preconditions = review_preconditions or SubmittedRepairPreconditions(app.state.simulation_lookup)
    app.add_middleware(UploadLimitMiddleware, max_bytes=config.upload_max_bytes)
    app.dependency_overrides[get_settings] = lambda: config
    app.include_router(router, prefix="/api/v1")

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        candidate = request.headers.get("X-Request-ID", "")
        # PROPOSED operational validation: printable ASCII correlation IDs <=128 chars.
        request.state.request_id = candidate if candidate and len(candidate) <= 128 and all(32 < ord(c) < 127 for c in candidate) else f"req_{uuid4().hex}"
        try:
            response = await call_next(request)
        except Exception as error:
            # Do not log exception messages, SQL parameters, request bodies or locals.
            frames = " > ".join(f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"
                                for frame in traceback.extract_tb(error.__traceback__))
            logging.getLogger("procuremind.errors").error(
                "Unhandled request request_id=%s error_type=%s frames=%s",
                request.state.request_id, type(error).__name__, frames)
            response = failure(ApiError(500, "INTERNAL_ERROR", "Internal server error"), request.state.request_id)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(ApiError)
    async def api_error(request: Request, error: ApiError):
        return failure(error, request.state.request_id)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        # Do not echo input values, document text, or validator contexts.
        details = [ErrorDetail(field=".".join(str(v) for v in e["loc"]), reason="Invalid or unknown field") for e in error.errors()]
        return failure(ApiError(400, "VALIDATION_ERROR", "The request contains invalid fields", details=details), request.state.request_id)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        codes = {401: "AUTHENTICATION_REQUIRED", 403: "FORBIDDEN", 404: "RESOURCE_NOT_FOUND", 413: "FILE_TOO_LARGE", 415: "UNSUPPORTED_MEDIA_TYPE", 429: "RATE_LIMITED"}
        # Uncataloged framework statuses retain HTTP status; fallback code is PROPOSED.
        code = codes.get(error.status_code, "VALIDATION_ERROR" if error.status_code < 500 else "INTERNAL_ERROR")
        response = failure(ApiError(error.status_code, code, "Request could not be completed"), request.state.request_id)
        response.headers.update(error.headers or {})
        return response

    @app.get("/api/v1/health", response_model=Envelope[HealthData], tags=["foundation"])
    def health(request: Request):
        # PROPOSED health payload; envelope itself is specified by Section 2.
        return success(HealthData(status="ok", demo_mode=config.demo_mode), request.state.request_id)

    def custom_openapi():
        if app.openapi_schema is None:
            from app.schemas.shared import Envelope
            schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
            for path, methods in schema["paths"].items():
                for method, operation in methods.items():
                    validation_ref = operation.get("responses", {}).get("422", {}).get("content", {}).get("application/json", {}).get("schema", {}).get("$ref")
                    if validation_ref == "#/components/schemas/HTTPValidationError":
                        operation["responses"].pop("422")
                    for status, description in ((400, "Validation error"), (401, "Authentication required"), (403, "Forbidden"), (404, "Resource not found"), (409, "Version/state/idempotency conflict"), (500, "Internal error")):
                        operation["responses"].setdefault(str(status), {"description": description,
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/EnvelopeError"}}}})
                    if method == "post" and path.endswith("/documents"):
                        for status in (413, 415, 422):
                            operation["responses"][str(status)] = {"description": "PDF upload rejection", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/EnvelopeError"}}}}
                    if method == "post" and path.endswith(("/challenges", "/repair-proposals")):
                        for status in (422, 429, 502, 504):
                            operation["responses"][str(status)] = {"description": "Decision evidence/provider error", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/EnvelopeError"}}}}
                        operation["responses"]["429"]["headers"] = {"Retry-After": {"description": "Provider-requested delay when available", "schema": {"type": "string"}}}
                    if method == "patch" and ("/challenges/" in path or "/repair-proposals/" in path):
                        operation["responses"]["422"] = {"description": "Required evidence or draft grounding failed", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/EnvelopeError"}}}}
            error_schema = Envelope[None].model_json_schema(ref_template="#/components/schemas/{model}")
            definitions = error_schema.pop("$defs", {})
            schema.setdefault("components", {}).setdefault("schemas", {}).update(definitions)
            schema["components"]["schemas"]["EnvelopeError"] = error_schema
            app.openapi_schema = schema
        return app.openapi_schema
    app.openapi = custom_openapi
    return app


app = create_app()
