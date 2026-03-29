"""
Context processors for the project.
"""

from __future__ import annotations

from apps.core.translation_service import get_admin_translation

# Keys used in admin UI context (administration.*)
ADMIN_BUTTON_KEYS = (
    "btn_save",
    "btn_save_and_add_another",
    "btn_save_and_continue_editing",
    "btn_delete",
    "menu_view_site",
    "menu_change_password",
    "menu_logout",
    "theme_light",
    "theme_dark",
    "theme_system",
    "login_welcome",
    "login_btn",
    "login_forgot_password",
    "logout_title",
    "logout_subtitle",
    "logout_btn",
    "return_to_site",
)


def admin_submit_button_translations(request):
    """
    Add administration submit-line button labels to context for admin pages,
    so templates can use {{ admin_btn_save }} etc. without a custom template tag.
    """
    if not getattr(request, "path", "").startswith("/admin/"):
        return {}
    out = {}
    for short_key in ADMIN_BUTTON_KEYS:
        full_key = f"administration.{short_key}"
        # Defaults in English for fallback
        defaults = {
            "btn_save": "Save",
            "btn_save_and_add_another": "Save and add another",
            "btn_save_and_continue_editing": "Save and continue editing",
            "btn_delete": "Delete",
            "menu_view_site": "View site",
            "menu_change_password": "Change password",
            "menu_logout": "Log out",
            "theme_light": "Light",
            "theme_dark": "Dark",
            "theme_system": "System",
            "login_welcome": "Welcome back to",
            "login_btn": "Log in",
            "login_forgot_password": "Forgotten your password or username?",
            "logout_title": "You have been successfully logged out from the administration",
            "logout_subtitle": "Thanks for spending some quality time with the web site today.",
            "logout_btn": "Log in again",
            "return_to_site": "Return to site",
        }
        out[f"admin_{short_key}"] = get_admin_translation(
            request, full_key, defaults.get(short_key, "")
        )
    return out
