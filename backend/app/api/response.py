"""PROPOSED envelope helpers; nested shapes are not contract-verified."""
from typing import Any

from fastapi.responses import JSONResponse


def success_response(data: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": True, "data": data, "error": None, "meta": {}},
    )


def error_response(status_code: int, message: str) -> JSONResponse:
    # PROPOSED: error.message and empty meta must be checked against v1.1.
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "data": None,
                 "error": {"message": message}, "meta": {}},
    )
