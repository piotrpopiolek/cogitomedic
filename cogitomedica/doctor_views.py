"""
Doctor panel: list of medical documents and document detail with Befund form.
Requires authenticated user with role DOCTOR, ADMIN, or MANAGER (nadzór).
Staff login (HTML) shares Django session with API auth.

UI strings and error messages use the ``doctor`` translation category (see
``doctor_ui.json`` / ``TranslationValue``).
"""

from __future__ import annotations

import logging
from uuid import UUID

from django.contrib import admin
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from apps.core.exceptions import DomainError
from apps.intake.models import IntakeStatus
from apps.medical.external_pdf_service import (
    GateResult,
    check_external_pdf_gate,
    create_attachment_records,
)
from apps.medical.models import (
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentSourceType,
)
from apps.medical.services import (
    acquire_document_lock,
    check_doctor_queue_entry_access,
    create_medical_document_without_intake,
    create_or_get_medical_document,
    get_medical_document_context,
    list_doctor_work_queue,
    parse_medical_documents_list_params,
)
from apps.reception.models import Patient, QueueEntry
from apps.users.display import staff_user_display_name
from apps.users.models import ROLE_GROUP_NAME_MAP, StaffUser
from apps.core.translation_service import (
    get_doctor_ui,
    get_fitzpatrick_choices,
    resolve_other_message,
)

logger = logging.getLogger(__name__)


def _render_doctor(
    request: HttpRequest,
    template_name: str,
    context: dict,
    *,
    status: int = 200,
) -> HttpResponse:
    """Render doctor templates with admin/unfold base context."""
    merged_context = {
        **admin.site.each_context(request),
        **context,
    }
    return render(request, template_name, merged_context, status=status)


def _safe_redirect_next(request: HttpRequest, default_view_name: str):
    """Return redirect URL from next param if safe (same host), else default view name."""
    next_url = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if next_url and not url_has_allowed_host_and_scheme(next_url, request.get_host()):
        next_url = ""
    return redirect(next_url or default_view_name)


@require_http_methods(["GET", "POST"])
@csrf_protect
def doctor_login_view(request: HttpRequest) -> HttpResponse:
    """Staff login (DOCTOR/ADMIN/MANAGER). Same session as API. Redirects to /doctor/ or next."""
    if request.user.is_authenticated and _doctor_role_ok(request):
        next_url = (request.GET.get("next") or "").strip()
        if next_url and not url_has_allowed_host_and_scheme(
            next_url, request.get_host()
        ):
            next_url = ""
        return redirect(next_url or "doctor-list")
    lang = _get_doctor_lang(request)
    ui = get_doctor_ui(lang)
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_active and _doctor_role_ok_request(user):
            login(request, user)
            if request.POST.get("lang") in ("de", "en", "pl") or request.GET.get(
                "lang"
            ) in ("de", "en", "pl"):
                request.session["doctor_lang"] = request.POST.get(
                    "lang"
                ) or request.GET.get("lang")
            return _safe_redirect_next(request, "doctor-list")
        return render(
            request,
            "doctor/login.html",
            {
                **admin.site.each_context(request),
                "error": ui["login_error_invalid"],
                "next": (request.POST.get("next") or "").strip(),
                "ui": ui,
                "lang": lang,
            },
        )
    next_val = (request.GET.get("next") or "").strip()
    if next_val and not url_has_allowed_host_and_scheme(next_val, request.get_host()):
        next_val = ""
    return render(
        request,
        "doctor/login.html",
        {**admin.site.each_context(request), "next": next_val, "ui": ui, "lang": lang},
    )


def _doctor_role_ok_request(user) -> bool:
    return user.is_authenticated and (
        user.is_doctor or user.is_admin_role or user.is_manager
    )


@login_required(login_url="doctor-login")
@require_http_methods(["POST"])
@csrf_protect
def doctor_logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect("doctor-login")


def _doctor_role_ok(request: HttpRequest) -> bool:
    user = request.user
    return user.is_authenticated and (
        user.is_doctor or user.is_admin_role or user.is_manager
    )


def _get_doctor_lang(request: HttpRequest) -> str:
    """Język panelu: z GET ?lang= lub sesji, domyślnie 'de'."""
    lang = request.GET.get("lang") or request.session.get("doctor_lang", "de")
    return "en" if lang == "en" else "pl" if lang == "pl" else "de"


def _apply_doctor_lang(request: HttpRequest) -> str:
    """Ustaw język z GET w sesji (jeśli podany) i zwróć aktualny lang."""
    lang = _get_doctor_lang(request)
    if request.GET.get("lang") in ("de", "en", "pl"):
        request.session["doctor_lang"] = request.GET.get("lang")
    return lang


def _doctor_list_page_querystring(request: HttpRequest, *, target_page: int) -> str:
    """Rebuild GET query for doctor list with ``page`` set (omit ``page`` when ``target_page`` is 1)."""
    q = request.GET.copy()
    q.pop("lang", None)
    if target_page <= 1:
        q.pop("page", None)
    else:
        q["page"] = str(target_page)
    return q.urlencode()


def _doctor_filter_published_by_options() -> list[tuple[str, str]]:
    """Active staff in the ``Doctor`` role: ``(user_id, label)`` for the list filter."""
    qs = (
        StaffUser.objects.filter(
            groups__name=ROLE_GROUP_NAME_MAP["DOCTOR"],
            is_active=True,
        )
        .distinct()
        .order_by("last_name", "first_name", "username")
    )
    return [
        (
            str(u.id),
            (staff_user_display_name(u) or u.username or str(u.id)).strip(),
        )
        for u in qs
    ]


def _doctor_list_page_link_items(
    request: HttpRequest, *, num_pages: int, page: int
) -> list[dict[str, object]]:
    """Unfold-style elided page numbers (same algorithm as Django admin paginator)."""
    if num_pages <= 1:
        return []
    paginator = Paginator(range(num_pages), 1)
    items: list[dict[str, object]] = []
    for el in paginator.get_elided_page_range(page, on_each_side=3, on_ends=2):
        if isinstance(el, int):
            n = el
            items.append(
                {
                    "type": "page",
                    "number": n,
                    "query": _doctor_list_page_querystring(request, target_page=n),
                    "current": n == page,
                }
            )
        else:
            items.append({"type": "ellipsis"})
    return items


@login_required(login_url="doctor-login")
@require_http_methods(["GET"])
def doctor_list_view(request: HttpRequest) -> HttpResponse:
    """List medical documents (work queue) with optional filters."""
    if not _doctor_role_ok(request):
        return redirect("doctor-login")
    list_params = parse_medical_documents_list_params(request.GET)
    list_items, total = list_doctor_work_queue(
        **list_params,
        user=request.user,
    )
    page = list_params["page"]
    page_size = list_params["page_size"]
    num_pages = (total + page_size - 1) // page_size if total > 0 else 1
    has_previous = page > 1 and num_pages > 1
    has_next = page < num_pages
    prev_query = _doctor_list_page_querystring(request, target_page=page - 1)
    next_query = _doctor_list_page_querystring(request, target_page=page + 1)
    lang = _apply_doctor_lang(request)
    if request.GET.get("lang"):
        query = request.GET.copy()
        query.pop("lang", None)
        url = request.path + ("?" + query.urlencode() if query else "")
        return redirect(url or "doctor-list")
    return _render_doctor(
        request,
        "doctor/list.html",
        {
            "items": list_items,
            "api_base": "/api/v1",
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "num_pages": num_pages,
                "has_previous": has_previous,
                "has_next": has_next,
                "prev_query": prev_query,
                "next_query": next_query,
                "page_link_items": _doctor_list_page_link_items(
                    request, num_pages=num_pages, page=page
                ),
            },
            "filters": {
                "status": list_params["status"] or "",
                "queue_date": request.GET.get("queue_date") or "",
                "patient_search": list_params["patient_search"] or "",
                "published_by_user_id": (
                    str(list_params["published_by_user_id"])
                    if list_params["published_by_user_id"]
                    else ""
                ),
                "scope": list_params["scope"],
            },
            "published_by_doctor_options": _doctor_filter_published_by_options(),
            "paper_intake_create_cta": resolve_other_message(
                request,
                "doctor.paper_intake_create_cta",
                "Papierdokument erstellen",
            ),
            "ui": get_doctor_ui(lang),
            "lang": lang,
        },
    )


def _render_no_intake_action_page(
    request: HttpRequest,
    *,
    queue_entry_id: UUID,
    lang: str,
    ui: dict[str, str],
    error_message: str | None = None,
    status: int = 200,
) -> HttpResponse:
    return _render_doctor(
        request,
        "doctor/no_intake_action.html",
        {
            "queue_entry_id": str(queue_entry_id),
            "ui": ui,
            "lang": lang,
            "title": resolve_other_message(
                request,
                "doctor.paper_intake_no_digital_title",
                "Keine digitale Anamnese vorhanden",
            ),
            "message": resolve_other_message(
                request,
                "doctor.paper_intake_no_digital_message",
                (
                    "Für diesen Eintrag liegt keine digitale Anamnese vor. "
                    "Sie können jetzt ein medizinisches Dokument im Papiermodus erstellen."
                ),
            ),
            "submit_label": resolve_other_message(
                request,
                "doctor.paper_intake_create_cta",
                "Papierdokument erstellen",
            ),
            "cancel_label": resolve_other_message(
                request,
                "doctor.paper_intake_cancel",
                "Zurück zur Liste",
            ),
            "error_message": error_message,
        },
        status=status,
    )


@login_required(login_url="doctor-login")
@require_http_methods(["GET"])
def doctor_open_by_queue_view(
    request: HttpRequest, queue_entry_id: UUID
) -> HttpResponse:
    """Open queue entry in Befund flow (requires SUBMITTED digital intake or existing document).

    If a medical document with ``source_type=EXTERNAL_UPLOAD`` already exists for this
    queue entry, redirect straight to document detail — do not run Befund intake gates
    or :func:`~apps.medical.services.create_or_get_medical_document`.
    """
    if not _doctor_role_ok(request):
        return redirect("doctor-login")
    lang = _get_doctor_lang(request)
    ui = get_doctor_ui(lang)
    try:
        entry = QueueEntry.objects.select_related(
            "intake_form", "daily_queue", "medical_document"
        ).get(id=queue_entry_id)
        check_doctor_queue_entry_access(entry, request.user)
    except ObjectDoesNotExist:
        return _render_doctor(
            request,
            "doctor/error.html",
            {
                "message": ui["error_queue_entry_not_found"],
                "ui": ui,
                "lang": lang,
            },
            status=404,
        )
    ext_doc = (
        MedicalDocument.objects.filter(
            queue_entry_id=entry.id,
            source_type=MedicalDocumentSourceType.EXTERNAL_UPLOAD,
        )
        .only("id")
        .first()
    )
    if ext_doc is not None:
        url = reverse(
            "doctor-document-detail",
            kwargs={"medical_document_id": ext_doc.id},
        )
        return HttpResponseRedirect(url + "?lang=" + lang)

    existing_doc = getattr(entry, "medical_document", None)
    if existing_doc is not None:
        doc = existing_doc
    else:
        intake_form = getattr(entry, "intake_form", None)
        if intake_form is None:
            if QueueEntry.objects.filter(
                id=entry.id,
                paper_intake_authorization__isnull=False,
            ).exists():
                return _render_no_intake_action_page(
                    request,
                    queue_entry_id=entry.id,
                    lang=lang,
                    ui=ui,
                )
            return _render_doctor(
                request,
                "doctor/error.html",
                {
                    "message": ui["error_no_intake_for_entry"],
                    "ui": ui,
                    "lang": lang,
                },
                status=400,
            )
        else:
            form_status = getattr(intake_form, "form_status", None)
            if form_status == IntakeStatus.REOPENED:
                return _render_doctor(
                    request,
                    "doctor/error.html",
                    {
                        "message": ui["error_intake_reopened_patient_editing"],
                        "ui": ui,
                        "lang": lang,
                    },
                    status=400,
                )
            if form_status != IntakeStatus.SUBMITTED:
                return _render_doctor(
                    request,
                    "doctor/error.html",
                    {
                        "message": ui["error_intake_not_submitted"],
                        "ui": ui,
                        "lang": lang,
                    },
                    status=400,
                )
            doc = create_or_get_medical_document(
                queue_entry_id=entry.id,
                intake_form_id=intake_form.id,
                created_by_user_id=request.user.id,
            )
    url = reverse("doctor-document-detail", kwargs={"medical_document_id": doc.id})
    return HttpResponseRedirect(url + "?lang=" + lang)


@login_required(login_url="doctor-login")
@require_http_methods(["POST"])
@csrf_protect
def doctor_create_no_intake_view(
    request: HttpRequest, queue_entry_id: UUID
) -> HttpResponse:
    """Create paper medical document from doctor UI (explicit T2 action)."""
    if not _doctor_role_ok(request):
        return redirect("doctor-login")
    lang = _get_doctor_lang(request)
    ui = get_doctor_ui(lang)
    try:
        entry = QueueEntry.objects.select_related("daily_queue").get(id=queue_entry_id)
        check_doctor_queue_entry_access(entry, request.user)
    except ObjectDoesNotExist:
        return _render_doctor(
            request,
            "doctor/error.html",
            {
                "message": ui["error_queue_entry_not_found"],
                "ui": ui,
                "lang": lang,
            },
            status=404,
        )
    try:
        doc = create_medical_document_without_intake(
            queue_entry_id=entry.id,
            created_by_user_id=request.user.id,
        )
    except DomainError as exc:
        if (
            exc.api_message_key
            == "other.domain.medical_document_already_exists_for_queue_entry"
        ):
            existing_doc = MedicalDocument.objects.filter(
                queue_entry_id=entry.id
            ).first()
            if existing_doc is not None:
                url = reverse(
                    "doctor-document-detail",
                    kwargs={"medical_document_id": existing_doc.id},
                )
                return HttpResponseRedirect(url + "?lang=" + lang)
        return _render_no_intake_action_page(
            request,
            queue_entry_id=entry.id,
            lang=lang,
            ui=ui,
            error_message=str(exc),
            status=400,
        )

    url = reverse("doctor-document-detail", kwargs={"medical_document_id": doc.id})
    return HttpResponseRedirect(url + "?lang=" + lang)


@login_required(login_url="doctor-login")
@require_http_methods(["GET"])
def doctor_document_detail_view(
    request: HttpRequest, medical_document_id: UUID
) -> HttpResponse:
    """Document detail with intake summary and Befund form (data for client-side API calls)."""
    if not _doctor_role_ok(request):
        return redirect("doctor-login")
    lang = _get_doctor_lang(request)
    ui = get_doctor_ui(lang)
    try:
        context = get_medical_document_context(
            medical_document_id=medical_document_id,
            form_locale=request.GET.get("form_locale")
            or ("en-GB" if lang == "en" else "pl-PL" if lang == "pl" else "de-DE"),
            user=request.user,
        )
        doc = MedicalDocument.objects.get(pk=medical_document_id)
        patient_summary = (context.get("intake_summary") or {}).get("patient") or {}
        patient_pk = patient_summary.get("id")
        patient = Patient.objects.get(pk=patient_pk) if patient_pk else None
        if patient is None:
            raise ObjectDoesNotExist()
        external_readonly = doc.source_type == MedicalDocumentSourceType.EXTERNAL_UPLOAD
        if doc.status == MedicalDocStatus.PUBLISHED or external_readonly:
            gate = GateResult(
                passed=True,
                matched_files=(),
                error_message=None,
                skip_attachment_sync=True,
            )
        else:
            gate = check_external_pdf_gate(
                patient,
                error_no_file=ui["external_pdf_gate_no_file"],
                error_no_pdfs_in_folder=ui["external_pdf_gate_no_pdfs_in_folder"],
                error_ambiguous=ui["external_pdf_gate_ambiguous"],
                error_hidrive=ui["external_pdf_gate_hidrive_error"],
            )
        if not gate.passed:
            # 424: zależność zewnętrzna (HiDrive / PDF w folderze). Odróżnia od 422 przy
            # DomainError (np. brak snapshotu audytu papieru) — ten sam widok, inna przyczyna.
            logger.warning(
                "doctor_document_detail: external PDF gate blocked",
                extra={
                    "cogito_error_class": "external_pdf_gate",
                    "medical_document_id": str(medical_document_id),
                },
            )
            return _render_doctor(
                request,
                "doctor/error.html",
                {
                    "message": gate.error_message or ui["external_pdf_gate_no_file"],
                    "ui": ui,
                    "lang": lang,
                },
                status=424,
            )

        if external_readonly:
            granted, lock_holder = True, None
        else:
            granted, lock_holder = acquire_document_lock(
                medical_document_id=medical_document_id, user=request.user
            )
    except DomainError as exc:
        msg_key = exc.api_message_key or ""
        message = (
            resolve_other_message(request, msg_key, str(exc)) if msg_key else str(exc)
        )
        logger.warning(
            "doctor_document_detail: domain error",
            extra={
                "cogito_error_class": "domain_error",
                "api_message_key": msg_key or None,
                "medical_document_id": str(medical_document_id),
            },
        )
        return _render_doctor(
            request,
            "doctor/error.html",
            {
                "message": message,
                "ui": ui,
                "lang": lang,
            },
            status=422,
        )
    except ObjectDoesNotExist:
        return _render_doctor(
            request,
            "doctor/error.html",
            {
                "message": ui["error_document_not_found"],
                "ui": ui,
                "lang": lang,
            },
            status=404,
        )
    if not granted:
        message = resolve_other_message(
            request,
            "doctor.document_locked_error",
            (
                "Dieses Dokument wird gerade von {username} bearbeitet. "
                "Bitte versuchen Sie es später erneut."
            ),
            username=lock_holder or "…",
        )
        return _render_doctor(
            request,
            "doctor/error.html",
            {"message": message, "ui": ui, "lang": lang},
            status=423,
        )
    if not gate.skip_attachment_sync:
        create_attachment_records(doc, gate.matched_files)

    fitzpatrick_choices = get_fitzpatrick_choices(lang)
    authoring_locale = "en-GB" if lang == "en" else "pl-PL" if lang == "pl" else "de-DE"
    if "authoring_locale" not in context:
        context["authoring_locale"] = authoring_locale
    body_map_rel = static("tablet/body.jpg")
    doctor_external_upload_pdf_href = None
    external_upload_load_attachment_panel = False
    if external_readonly:
        # Doctors do not preview reception DRAFT uploads (processed off-platform).
        # Preview is offered only after publish, or the last published PDF during revision.
        if doc.status == MedicalDocStatus.PUBLISHED:
            doctor_external_upload_pdf_href = request.build_absolute_uri(
                reverse(
                    "medical-document-preview-pdf",
                    kwargs={"medical_document_id": doc.id},
                )
            )
        elif doc.published_version_no is not None:
            doctor_external_upload_pdf_href = request.build_absolute_uri(
                reverse(
                    "medical-document-preview-pdf",
                    kwargs={"medical_document_id": doc.id},
                )
            )
        # Attachment list/iframe uses doctor-accessible APIs; block for doctors pre-publish.
        if getattr(request.user, "is_doctor", False):
            external_upload_load_attachment_panel = doc.status != MedicalDocStatus.DRAFT
        else:
            external_upload_load_attachment_panel = True
    panel_data = {
        "documentId": str(medical_document_id),
        "apiBase": "/api/v1",
        "context": context,
        "ui": ui,
        "listUrl": request.build_absolute_uri(reverse("doctor-list")),
        "bodyMapImageUrl": request.build_absolute_uri(body_map_rel),
        "externalUploadReadOnly": external_readonly,
        "externalUploadLoadAttachmentPanel": external_upload_load_attachment_panel,
    }
    return _render_doctor(
        request,
        "doctor/detail.html",
        {
            "document_id": str(medical_document_id),
            "panel_data": panel_data,
            "api_base": "/api/v1",
            "fitzpatrick_choices": fitzpatrick_choices,
            "ui": ui,
            "lang": lang,
            "external_pdf_hidrive_warning": (
                gate.error_message if gate.passed and gate.error_message else None
            ),
            "doctor_external_upload_readonly": external_readonly,
            "doctor_external_upload_pdf_href": doctor_external_upload_pdf_href,
            "doctor_external_upload_has_pending_revision": bool(
                external_readonly and doc.has_pending_revision
            ),
        },
    )
