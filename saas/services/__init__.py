# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
SaaS Services
=============
Helpers for handling structured uploads and SaaS-style records:
- SaaSRecordFormatter: Format raw API records as natural language
- StructuredFileExtractor: Extract records from Excel/JSON/CSV files
"""

from .saas_record_formatter import format_record, format_excel_row, format_json_record, FORMATTERS
from .structured_file_extractor import (
    detect_structured_excel,
    detect_structured_csv,
    detect_structured_json,
    extract_excel_records,
    extract_csv_records,
    extract_json_records,
    get_records_in_batches,
    MAX_RECORDS_PER_FILE,
    MIN_ROWS_FOR_RECORD_EXTRACTION
)

__all__ = [
    "format_record",
    "format_excel_row",
    "format_json_record",
    "FORMATTERS",
    "get_records_in_batches",
    "MAX_RECORDS_PER_FILE",
    "MIN_ROWS_FOR_RECORD_EXTRACTION",
]
