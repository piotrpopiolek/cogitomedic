from apps.reception.api_views_split.devices import (
    tablet_device_detail_view,
    tablet_device_heartbeat_view,
    tablet_devices_view,
)
from apps.reception.api_views_split.dictionaries import (
    clinic_site_detail_view,
    clinic_sites_view,
    consulting_room_detail_view,
    consulting_rooms_view,
)
from apps.reception.api_views_split.patients import (
    patient_contact_history_view,
    patient_detail_view,
    patients_view,
)
from apps.reception.api_views_split.queues import (
    daily_queue_detail_view,
    daily_queue_entries_view,
    daily_queues_view,
    queue_entry_detail_view,
    queue_entry_sessions_view,
)

__all__ = [
    "clinic_site_detail_view",
    "clinic_sites_view",
    "consulting_room_detail_view",
    "consulting_rooms_view",
    "daily_queue_detail_view",
    "daily_queue_entries_view",
    "daily_queues_view",
    "patient_contact_history_view",
    "patient_detail_view",
    "patients_view",
    "queue_entry_detail_view",
    "queue_entry_sessions_view",
    "tablet_device_detail_view",
    "tablet_device_heartbeat_view",
    "tablet_devices_view",
]
