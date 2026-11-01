from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for expected application errors mapped to HTTP responses."""

    status_code = 400
    code = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details


class AuthenticationError(AppError):
    status_code = 401
    code = "authentication_required"


class InvalidCredentialsError(AuthenticationError):
    code = "invalid_credentials"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"


class UnsupportedMediaTypeError(AppError):
    status_code = 415
    code = "unsupported_media_type"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"


class TrainingError(Exception):
    """Machine learning pipeline failure with a user-safe message."""


class DatasetValidationError(AppError):
    status_code = 422
    code = "invalid_dataset"
