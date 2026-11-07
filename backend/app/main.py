from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from app.api.response import ApiError, failure, success
from app.api.routes import router
from app.core.config import Settings, get_settings
from app.core.database import build_engine, session_factory
from app.schemas.shared import Envelope, ErrorDetail, HealthData


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = build_engine(config.database_url)
        app.state.session_factory = session_factory(engine)
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="ProcureMind V4.1", version="1.1", lifespan=lifespan,
        description="Shared foundation with human review, audit, and deterministic simulation APIs. Other business routers await owner integration. See contract gap register.")
    app.dependency_overrides[get_settings] = lambda: config
    app.include_router(router, prefix="/api/v1")

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        candidate = request.headers.get("X-Request-ID", "")
        # PROPOSED operational validation: printable ASCII correlation IDs <=128 chars.
        request.state.request_id = candidate if candidate and len(candidate) <= 128 and all(32 < ord(c) < 127 for c in candidate) else f"req_{uuid4().hex}"
        try:
            response = await call_next(request)
        except Exception:
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

    return app


app = create_app()
