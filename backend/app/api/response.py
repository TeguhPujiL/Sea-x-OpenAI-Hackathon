from datetime import datetime, timezone
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.schemas.shared import Envelope, ErrorBody, ErrorDetail, Meta


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, *, retryable: bool = False,
                 details: list[ErrorDetail] | None = None):
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or []


def meta(request_id: str) -> Meta:
    return Meta(request_id=request_id, timestamp=datetime.now(timezone.utc), api_version="v1")


def success(data: Any, request_id: str, status: int = 200) -> JSONResponse:
    body = Envelope[Any](success=True, data=data, error=None, meta=meta(request_id))
    return JSONResponse(jsonable_encoder(body.model_dump(mode="json")), status_code=status)


def failure(error: ApiError, request_id: str) -> JSONResponse:
    body = Envelope[Any](success=False, data=None,
        error=ErrorBody(code=error.code, message=error.message, details=error.details,
                        retryable=error.retryable), meta=meta(request_id))
    return JSONResponse(body.model_dump(mode="json"), status_code=error.status)
