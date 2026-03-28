from __future__ import annotations

from json import JSONDecodeError
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from pydantic import ValidationError

from apps.core.api_utils import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    get_scoped_clinic_site_ids,
    json_domain_error,
    json_error,
    parse_bool_query,
    read_json_body,
    require_auth,
    require_user_role,
    safe_parse_positive_int,
)
from apps.core.exceptions import DomainError, InvalidRequestBodyEncoding
from apps.reception.api_schemas import (
    CreatePatientRequest,
    PatientsListQuery,
    UpdatePatientRequest,
)
from apps.reception.models import Patient
from apps.reception.services import create_or_update_patient_manual



def _serialize_patient(patient: Patient) -> dict:
    return {
        "id": str(patient.id),
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "date_of_birth": patient.date_of_birth.isoformat(),
        "phone": patient.phone,
        "email": patient.email,
        "doctolib_patient_id": patient.doctolib_patient_id,
        "street": patient.street,
        "city": patient.city,
        "postal_code": patient.postal_code,
        "country_code": patient.country_code,
        "is_active": patient.is_active,
        "created_at": patient.created_at.isoformat(),
        "updated_at": patient.updated_at.isoformat(),
    }


@require_auth
def patients_view(request: HttpRequest) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN", "DOCTOR"})
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

        scope_ids = get_scoped_clinic_site_ids(request.user)
        if scope_ids is not None:
            if not scope_ids:
                return JsonResponse(
                    {
                        "items": [],
                        "pagination": {
                            "page": 1,
                            "page_size": DEFAULT_LIST_LIMIT,
                            "total": 0,
                        },
                    }
                )
            qs = qs.filter(
                Q(clinic_sites__id__in=scope_ids)
                | Q(queue_entries__daily_queue__clinic_site_id__in=scope_ids)
            ).distinct()
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
        doctolib_patient_id = request.GET.get("doctolib_patient_id")
        if doctolib_patient_id:
            qs = qs.filter(doctolib_patient_id=doctolib_patient_id)
        is_active = parse_bool_query(request.GET.get("is_active"))
        if request.GET.get("is_active") is not None and is_active is None:
            return json_error("other.api.invalid_is_active", status=400)
        if is_active is not None:
            qs = qs.filter(is_active=is_active)
        page = safe_parse_positive_int(request.GET.get("page"), default=1, maximum=10_000)
        page_size = safe_parse_positive_int(
            request.GET.get("page_size"),
            default=DEFAULT_LIST_LIMIT,
            maximum=MAX_LIST_LIMIT,
        )
        total = qs.count()
        start = (page - 1) * page_size
        end = start + page_size
        items = [_serialize_patient(patient) for patient in qs[start:end]]
        return JsonResponse({"items": items, "pagination": {"page": page, "page_size": page_size, "total": total}})

    if request.method == "POST":
        try:
            body = CreatePatientRequest.model_validate(read_json_body(request))
        except JSONDecodeError:
            return json_error("other.api.invalid_json_payload", status=400)
        except InvalidRequestBodyEncoding as exc:
            return json_domain_error(exc)
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
            patient.save(update_fields=update_fields)
        except IntegrityError:
            return json_error("other.api.patient_uniqueness_conflict", status=409)
        except DomainError as exc:
            return json_domain_error(exc, status=400)
        return JsonResponse({"patient": _serialize_patient(patient)}, status=201)

    return json_error("other.api.method_not_allowed", status=405)


@require_auth
def patient_detail_view(request: HttpRequest, patient_id: UUID) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN", "DOCTOR"})
    if role_error:
        return role_error
    if request.method not in ("GET", "PATCH"):
        return json_error("other.api.method_not_allowed", status=405)
    
    if request.method == "PATCH" and request.user.is_doctor:
        return json_error("other.api.method_not_allowed_for_role", status=403)

    try:
        qs = Patient.objects.all()
        scope_ids = get_scoped_clinic_site_ids(request.user)
        if scope_ids is not None:
            if not scope_ids:
                return json_error("other.api.patient_not_found", status=404)
            qs = qs.filter(
                Q(clinic_sites__id__in=scope_ids)
                | Q(queue_entries__daily_queue__clinic_site_id__in=scope_ids)
            ).distinct()
        patient = qs.get(id=patient_id)
    except ObjectDoesNotExist:
        return json_error("other.api.patient_not_found", status=404)

    if request.method == "GET":
        return JsonResponse(_serialize_patient(patient))

    try:
        body = UpdatePatientRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("other.api.invalid_json_payload", status=400)
    except InvalidRequestBodyEncoding as exc:
        return json_domain_error(exc)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    fields_set = body.model_fields_set
    if not fields_set:
        return json_error("other.api.provide_field_to_update", status=400)
    identity_or_contact_fields = {
        "first_name",
        "last_name",
        "date_of_birth",
        "phone",
        "email",
        "doctolib_patient_id",
    }

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
        if "is_active" in fields_set and body.is_active is not None:
            patient.is_active = body.is_active
            update_fields.append("is_active")
        if len(update_fields) > 1:
            patient.save(update_fields=update_fields)
    except IntegrityError:
        return json_error("other.api.patient_uniqueness_conflict", status=409)
    except DomainError as exc:
        return json_domain_error(exc, status=400)

    return JsonResponse(_serialize_patient(patient))
