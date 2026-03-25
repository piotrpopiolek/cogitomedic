class DomainError(Exception):
    """Base exception for domain-level validation and business errors."""

    __slots__ = ("api_message_key",)

    def __init__(self, message: str, *, api_message_key: str | None = None) -> None:
        super().__init__(message)
        self.api_message_key = api_message_key


class StateTransitionError(DomainError):
    """Raised when an invalid status transition is requested."""


class IdempotencyConflictError(DomainError):
    """Raised when request idempotency input is invalid."""


class InvalidRequestBodyEncoding(Exception):
    """Raised when request body cannot be decoded as UTF-8."""
