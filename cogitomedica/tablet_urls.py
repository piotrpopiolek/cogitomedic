from django.urls import path

from cogitomedica.tablet_views import (
    tablet_entry_start_view,
    tablet_home_view,
    tablet_login_view,
    tablet_logout_view,
    tablet_queue_entries_view,
)

app_name = "tablet"

urlpatterns = [
    path("login/", tablet_login_view, name="login"),
    path("logout/", tablet_logout_view, name="logout"),
    path("", tablet_home_view, name="home"),
    path("queue/<uuid:daily_queue_id>/", tablet_queue_entries_view, name="queue_entries"),
    path("entry/<uuid:queue_entry_id>/", tablet_entry_start_view, name="entry_start"),
]
