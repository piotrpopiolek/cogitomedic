from __future__ import annotations

from json import JSONDecodeError

from django.contrib.auth import authenticate, login, logout
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from pydantic import ValidationError

from apps.core.api_utils import json_error, read_json_body
from apps.users.api_schemas import AuthLoginRequest


def _user_payload(request: HttpRequest) -> dict:
    user = request.user
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "role": getattr(user, "role", None),
        "preferred_locale": getattr(user, "preferred_locale", None),
        "is_authenticated": bool(user.is_authenticated),
    }


@csrf_exempt
def auth_login_view(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return json_error("Method not allowed.", status=405)

    try:
        body = AuthLoginRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    user = authenticate(request, username=body.username, password=body.password)
    if user is None or not user.is_active:
        return json_error("Invalid credentials.", status=401)

    login(request, user)
    return JsonResponse(
        {
            "user": _user_payload(request),
            "session_expires_in_seconds": request.session.get_expiry_age(),
        },
        status=200,
    )


@csrf_exempt
def auth_logout_view(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return json_error("Method not allowed.", status=405)

    logout(request)
    return JsonResponse({"ok": True}, status=200)


def auth_me_view(request: HttpRequest) -> JsonResponse:
    if request.method != "GET":
        return json_error("Method not allowed.", status=405)
    if not request.user.is_authenticated:
        return json_error("Authentication required.", status=401)

    return JsonResponse({"user": _user_payload(request)}, status=200)
