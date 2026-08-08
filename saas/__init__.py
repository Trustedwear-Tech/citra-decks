"""
SaaS Integration Module
=======================
Handles SaaS data processing:
- Vault connections management
- Structured file extraction
- Webhook processing
"""

from .services.saas_record_formatter import format_record, FORMATTERS

__all__ = [
    "FORMATTERS",
]
