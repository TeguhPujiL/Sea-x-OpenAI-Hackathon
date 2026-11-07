from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from app.api.response import error_response, success_response
from app.api.routes import router
from app.core.config import get_settings
from app.core.database import build_engine, build_session_factory


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = build_engine(get_settings().database_url)
    app.state.session_factory = build_session_factory(engine)
    try:
        yield
    finally:
        engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="ProcureMind V4.1 - Unverified Foundation",
        version="0.1.0", lifespan=lifespan,
        description="Primary API Contract v1.1 unavailable; wire shapes are PROPOSED.",
    )
    app.include_router(router, prefix="/api/v1")

    @app.get("/api/v1/health", tags=["foundation"])
    def health():
        """Process liveness only; PROPOSED data shape pending contract verification."""
        return success_response({"status": "ok"})

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        response = error_response(exc.status_code, str(exc.detail))
        response.headers.update(exc.headers or {})
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError):
        return error_response(422, "Request validation failed")

    @app.exception_handler(Exception)
    async def unexpected_error(_request: Request, _exc: Exception):
        return error_response(500, "Internal server error")

    return app


app = create_app()
