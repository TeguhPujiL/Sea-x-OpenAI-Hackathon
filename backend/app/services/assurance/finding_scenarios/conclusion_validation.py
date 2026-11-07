"""Safe, actionable validation details for the opt-in conclusion route only."""
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from app.api.response import ApiError
from app.schemas.shared import ErrorDetail


class ConclusionValidationRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def validated(request):
            try:
                return await handler(request)
            except RequestValidationError as error:
                details = []
                for item in error.errors():
                    field = ".".join(str(part) for part in item["loc"])
                    kind = item["type"]
                    if field == "body.decision_reason":
                        reason = {
                            "string_too_short": "Use at least 20 characters and four words for the decision reason.",
                            "decision_reason_minimum": "Use at least 20 characters and four words for the decision reason.",
                            "string_too_long": "Use no more than 4000 characters for the decision reason.",
                            "missing": "A decision reason is required.",
                            "string_type": "The decision reason must be text.",
                        }.get(kind, "The decision reason has an invalid format.")
                    else:
                        reason = {"missing": "This field is required.", "extra_forbidden": "Unknown field is not permitted."}.get(kind, "Invalid field value.")
                    # Never echo input, validator context or document text.
                    details.append(ErrorDetail(field=field, reason=reason))
                raise ApiError(400, "VALIDATION_ERROR", "The procurement decision contains invalid fields", details=details) from None

        return validated
