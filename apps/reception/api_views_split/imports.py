from __future__ import annotations

from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, JsonResponse

from apps.core.api_utils import (
    json_error,
    parse_list_limit,
    require_auth,
    require_user_role,
)
from apps.reception.models import PatientImportBatch, PatientImportError


def _serialize_batch(batch: PatientImportBatch) -> dict:
    return {
        "id": str(batch.id),
        "source_file_name": batch.source_file_name,
        "source_file_sha256": batch.source_file_sha256,
        "import_type": batch.import_type,
        "source_system": batch.source_system,
        "status": batch.status,
        "total_rows": batch.total_rows,
        "inserted_rows": batch.inserted_rows,
        "matched_rows": batch.matched_rows,
        "skipped_already_present_count": batch.skipped_already_present_count,
        "error_rows": batch.error_rows,
        "created_by_user_id": str(batch.created_by_user_id),
        "created_at": batch.created_at.isoformat(),
        "finished_at": batch.finished_at.isoformat() if batch.finished_at else None,
    }


def _serialize_error(error: PatientImportError) -> dict:
    return {
        "id": str(error.id),
        "batch_id": str(error.batch_id),
        "row_number": error.row_number,
        "error_code": error.error_code,
        "error_message": error.error_message,
        "raw_row": error.raw_row,
        "created_at": error.created_at.isoformat(),
    }


def _visible_batches(request: HttpRequest):
    qs = PatientImportBatch.objects.all().order_by("-created_at")
    if request.user.is_admin_role:
        return qs
    return qs.filter(created_by_user=request.user)


@require_auth
def import_batches_view(request: HttpRequest) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN"})
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("other.api.method_not_allowed", status=405)

    limit = parse_list_limit(request.GET.get("limit"))
    items = [_serialize_batch(batch) for batch in _visible_batches(request)[:limit]]
    return JsonResponse({"items": items})


@require_auth
def import_batch_detail_view(request: HttpRequest, batch_id: UUID) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN"})
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("other.api.method_not_allowed", status=405)

    try:
        batch = _visible_batches(request).get(id=batch_id)
    except ObjectDoesNotExist:
        return json_error("other.api.import_batch_not_found", status=404)
    return JsonResponse(_serialize_batch(batch))


@require_auth
def import_batch_errors_view(request: HttpRequest, batch_id: UUID) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN"})
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("other.api.method_not_allowed", status=405)

    try:
        batch = _visible_batches(request).get(id=batch_id)
    except ObjectDoesNotExist:
        return json_error("other.api.import_batch_not_found", status=404)

    items = [
        _serialize_error(error)
        for error in batch.errors.all().order_by("row_number", "created_at")
    ]
    return JsonResponse({"items": items})
