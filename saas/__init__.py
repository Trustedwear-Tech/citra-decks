# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

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
