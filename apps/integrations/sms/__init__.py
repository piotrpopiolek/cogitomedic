"""SMS integration (SMSApi)."""

from apps.integrations.sms.client import SmsAdapter, SmsAdapterProtocol, get_sms_adapter

__all__ = ["get_sms_adapter", "SmsAdapter", "SmsAdapterProtocol"]
