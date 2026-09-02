"""Intake domain limits shared across services and tests."""

# Maximum decoded signature payload size (bytes) for patient signature upload.
SIGNATURE_MAX_SIZE = 2 * 1024 * 1024

# JSON ``schema_version`` for ``PatientIntakeForm.telederm_payload``.
TELEDERM_PAYLOAD_SCHEMA_VERSION = 1


def default_telederm_payload() -> dict[str, int]:
    """Empty telederm JSON still carries ``schema_version`` (not a bare ``{}``)."""
    return {"schema_version": TELEDERM_PAYLOAD_SCHEMA_VERSION}
