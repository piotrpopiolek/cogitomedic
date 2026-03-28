class DomainError(Exception):
    """Base exception for domain-level validation and business errors."""

    __slots__ = ("api_message_key", "api_message_params")

    def __init__(
        self,
        message: str,
        *,
        api_message_key: str | None = None,
        api_message_params: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.api_message_key = api_message_key
        self.api_message_params = api_message_params


class StateTransitionError(DomainError):
    """Raised when an invalid status transition is requested."""


class IdempotencyConflictError(DomainError):
    """Raised when request idempotency input is invalid."""


class InvalidRequestBodyEncoding(Exception):
    """Raised when the request body is too large or cannot be decoded as UTF-8."""

    __slots__ = ("api_message_key", "api_message_params", "http_status")

    def __init__(
        self,
        message: str,
        *,
        api_message_key: str | None = None,
        api_message_params: dict[str, object] | None = None,
        http_status: int = 400,
    ) -> None:
        super().__init__(message)
        self.api_message_key = api_message_key
        self.api_message_params = api_message_params
        self.http_status = http_status
