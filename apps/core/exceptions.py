class DomainError(Exception):
    """Base exception for domain-level validation and business errors."""


class StateTransitionError(DomainError):
    """Raised when an invalid status transition is requested."""


class IdempotencyConflictError(DomainError):
    """Raised when request idempotency input is invalid."""
