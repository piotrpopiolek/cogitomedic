from __future__ import annotations

from json import JSONDecodeError
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from pydantic import ValidationError

from apps.core.api_utils import (
    json_error,
    parse_bool_query,
    read_json_body,
    require_auth,
    require_user_role,
    safe_parse_positive_int,
)
from apps.core.exceptions import DomainError, InvalidRequestBodyEncoding, StateTransitionError
from apps.reception.api_schemas import (
    CreatePatientRequest,
    MergePatientRequest,
    PatientsListQuery,
    UpdatePatientRequest,
)
from apps.reception.models import Patient, PatientContactHistory
from apps.reception.services import (
    InvalidSourceActionError,
    SourceNotTemporaryError,
    TargetNotConfirmedError,
    create_or_update_patient_manual,
    merge_temporary_patient_into_confirmed,
)



def _serialize_patient(patient: Patient) -> dict:
    return {
        "id": str(patient.id),
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "date_of_birth": patient.date_of_birth.isoformat(),
        "phone": patient.phone,
        "email": patient.email,
        "doctolib_patient_id": patient.doctolib_patient_id,
        "identity_status": patient.identity_status,
        "identity_alert_created_at": (
            patient.identity_alert_created_at.isoformat() if patient.identity_alert_created_at else None
        ),
        "identity_resolution_due_at": (
            patient.identity_resolution_due_at.isoformat() if patient.identity_resolution_due_at else None
        ),
        "street": patient.street,
        "city": patient.city,
        "postal_code": patient.postal_code,
        "country_code": patient.country_code,
        "external_source": patient.external_source,
        "external_source_id": patient.external_source_id,
        "is_active": patient.is_active,
        "created_at": patient.created_at.isoformat(),
        "updated_at": patient.updated_at.isoformat(),
    }


def _serialize_contact_history(item: PatientContactHistory) -> dict:
    return {
        "id": str(item.id),
        "phone": item.phone,
        "email": item.email,
        "changed_at": item.changed_at.isoformat(),
        "changed_by_user_id": str(item.changed_by_user_id) if item.changed_by_user_id else None,
        "reason": item.reason,
    }


@require_auth
@csrf_exempt
def patients_view(request: HttpRequest) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN"})
    if role_error:
        return role_error
    if request.method == "GET":
        try:
            list_query = PatientsListQuery.model_validate(
                {"date_of_birth": request.GET.get("date_of_birth")}
            )
        except ValidationError as exc:
            return JsonResponse(
                {"error": "Validation error.", "details": exc.errors()}, status=400
            )
        qs = Patient.objects.all().order_by("-created_at")
        search = request.GET.get("search")
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
            )
        last_name = request.GET.get("last_name")
        if last_name:
            qs = qs.filter(last_name__icontains=last_name)
        if list_query.date_of_birth is not None:
            qs = qs.filter(date_of_birth=list_query.date_of_birth)
        phone = request.GET.get("phone")
        if phone:
            qs = qs.filter(phone__icontains=phone)
        identity_status = request.GET.get("identity_status")
        if identity_status:
            qs = qs.filter(identity_status=identity_status)
        doctolib_patient_id = request.GET.get("doctolib_patient_id")
        if doctolib_patient_id:
            qs = qs.filter(doctolib_patient_id=doctolib_patient_id)
        is_active = parse_bool_query(request.GET.get("is_active"))
        if request.GET.get("is_active") is not None and is_active is None:
            return json_error("Invalid is_active query parameter.", status=400)
        if is_active is not None:
            qs = qs.filter(is_active=is_active)
        page = safe_parse_positive_int(request.GET.get("page"), default=1, maximum=10_000)
        page_size = safe_parse_positive_int(request.GET.get("page_size"), default=20, maximum=200)
        total = qs.count()
        start = (page - 1) * page_size
        end = start + page_size
        items = [_serialize_patient(patient) for patient in qs[start:end]]
        return JsonResponse({"items": items, "pagination": {"page": page, "page_size": page_size, "total": total}})

    if request.method == "POST":
        try:
            body = CreatePatientRequest.model_validate(read_json_body(request))
        except JSONDecodeError:
            return json_error("Invalid JSON payload.", status=400)
        except InvalidRequestBodyEncoding:
            return json_error("Invalid request encoding.", status=400)
        except ValidationError as exc:
            return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
        try:
            patient = create_or_update_patient_manual(
                first_name=body.first_name,
                last_name=body.last_name,
                date_of_birth=body.date_of_birth,
                phone=body.phone,
                email=body.email,
                doctolib_patient_id=body.doctolib_patient_id,
                created_or_updated_by_user_id=request.user.id,
            )
            update_fields = ["updated_at"]
            patient.street = body.street
            update_fields.append("street")
            patient.city = body.city
            update_fields.append("city")
            patient.postal_code = body.postal_code
            update_fields.append("postal_code")
            patient.country_code = body.country_code
            update_fields.append("country_code")
            patient.external_source = body.external_source
            update_fields.append("external_source")
            patient.external_source_id = body.external_source_id
            update_fields.append("external_source_id")
            patient.save(update_fields=update_fields)
        except IntegrityError:
            return json_error("Patient uniqueness conflict.", status=409)
        except DomainError as exc:
            return json_error(str(exc), status=400)
        return JsonResponse(
            {
                "patient": _serialize_patient(patient),
                "identity_alert": {
                    "created": patient.identity_status == "TEMPORARY",
                    "due_at": (
                        patient.identity_resolution_due_at.isoformat() if patient.identity_resolution_due_at else None
                    ),
                },
            },
            status=201,
        )

    return json_error("Method not allowed.", status=405)


@require_auth
@csrf_exempt
def patient_detail_view(request: HttpRequest, patient_id: UUID) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN"})
    if role_error:
        return role_error
    if request.method not in ("GET", "PATCH"):
        return json_error("Method not allowed.", status=405)
    try:
        patient = Patient.objects.get(id=patient_id)
    except ObjectDoesNotExist:
        return json_error("Patient not found.", status=404)

    if request.method == "GET":
        return JsonResponse(_serialize_patient(patient))

    try:
        body = UpdatePatientRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except InvalidRequestBodyEncoding:
        return json_error("Invalid request encoding.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    fields_set = body.model_fields_set
    if not fields_set:
        return json_error("Provide at least one field to update.", status=400)
    identity_or_contact_fields = {
        "first_name",
        "last_name",
        "date_of_birth",
        "phone",
        "email",
        "doctolib_patient_id",
    }

    old_phone = patient.phone
    old_email = patient.email
    try:
        if identity_or_contact_fields.intersection(fields_set):
            patient = create_or_update_patient_manual(
                patient_id=patient.id,
                first_name=body.first_name if "first_name" in fields_set else patient.first_name,
                last_name=body.last_name if "last_name" in fields_set else patient.last_name,
                date_of_birth=body.date_of_birth if "date_of_birth" in fields_set else patient.date_of_birth,
                phone=body.phone if "phone" in fields_set else patient.phone,
                email=body.email if "email" in fields_set else patient.email,
                doctolib_patient_id=(
                    body.doctolib_patient_id if "doctolib_patient_id" in fields_set else patient.doctolib_patient_id
                ),
                created_or_updated_by_user_id=request.user.id,
            )
        update_fields: list[str] = ["updated_at"]
        if "street" in fields_set:
            patient.street = body.street
            update_fields.append("street")
        if "city" in fields_set:
            patient.city = body.city
            update_fields.append("city")
        if "postal_code" in fields_set:
            patient.postal_code = body.postal_code
            update_fields.append("postal_code")
        if "country_code" in fields_set:
            patient.country_code = body.country_code
            update_fields.append("country_code")
        if "external_source" in fields_set:
            patient.external_source = body.external_source
            update_fields.append("external_source")
        if "external_source_id" in fields_set:
            patient.external_source_id = body.external_source_id
            update_fields.append("external_source_id")
        if "is_active" in fields_set and body.is_active is not None:
            patient.is_active = body.is_active
            update_fields.append("is_active")
        if len(update_fields) > 1:
            patient.save(update_fields=update_fields)
    except IntegrityError:
        return json_error("Patient uniqueness conflict.", status=409)
    except DomainError as exc:
        return json_error(str(exc), status=400)

    if patient.phone != old_phone or patient.email != old_email:
        PatientContactHistory.objects.create(
            patient=patient,
            phone=old_phone,
            email=old_email,
            changed_by_user_id=request.user.id,
            reason=body.change_reason,
        )
    return JsonResponse(_serialize_patient(patient))


@require_auth
@csrf_exempt
def patient_contact_history_view(request: HttpRequest, patient_id: UUID) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN"})
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("Method not allowed.", status=405)
    try:
        Patient.objects.get(id=patient_id)
    except ObjectDoesNotExist:
        return json_error("Patient not found.", status=404)
    page = safe_parse_positive_int(request.GET.get("page"), default=1, maximum=10_000)
    page_size = safe_parse_positive_int(request.GET.get("page_size"), default=20, maximum=200)
    qs = PatientContactHistory.objects.filter(patient_id=patient_id).order_by("-changed_at")
    total = qs.count()
    start = (page - 1) * page_size
    end = start + page_size
    items = [_serialize_contact_history(item) for item in qs[start:end]]
    return JsonResponse({"items": items, "pagination": {"page": page, "page_size": page_size, "total": total}})


@require_auth
@csrf_exempt
def patient_merge_view(request: HttpRequest, patient_id: UUID) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN"})
    if role_error:
        return role_error
    if request.method != "POST":
        return json_error("Method not allowed.", status=405)
    try:
        body = MergePatientRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except InvalidRequestBodyEncoding:
        return json_error("Invalid request encoding.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
    try:
        result = merge_temporary_patient_into_confirmed(
            source_patient_id=patient_id,
            target_patient_id=body.target_patient_id,
            source_action=body.source_action,
            reason=body.reason,
            actor_user_id=request.user.id,
        )
    except ObjectDoesNotExist:
        return json_error("Patient not found.", status=404)
    except StateTransitionError as exc:
        return json_error(str(exc), status=409)
    except (SourceNotTemporaryError, TargetNotConfirmedError) as exc:
        return json_error(str(exc), status=422)
    except InvalidSourceActionError as exc:
        return json_error(str(exc), status=400)
    except DomainError as exc:
        return json_error(str(exc), status=400)
    return JsonResponse(
        {
            "merged": result.merged,
            "source_patient_id": str(result.source_patient_id),
            "target_patient_id": str(result.target_patient_id),
            "moved_entities": {
                "queue_entries": result.moved_queue_entries,
                "intake_forms": result.moved_intake_forms,
                "medical_documents": result.moved_medical_documents,
            },
            "identity_alert_closed": result.identity_alert_closed,
        }
    )
