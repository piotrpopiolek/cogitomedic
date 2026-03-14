"""SMS integration (SMSApi)."""
from apps.integrations.sms.client import get_sms_adapter, SmsAdapter

__all__ = ["get_sms_adapter", "SmsAdapter"]
