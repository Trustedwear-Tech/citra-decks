# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from validation_utils import serialize_validation_error_details


def test_serialize_validation_error_details_makes_exceptions_json_safe():
    error_details = [{
        "type": "value_error",
        "loc": ("body", "file"),
        "msg": "Value error, Expected UploadFile, received: <class 'str'>",
        "input": "[object Object]",
        "ctx": {
            "error": ValueError("Expected UploadFile, received: <class 'str'>"),
        },
    }]

    serialized = serialize_validation_error_details(error_details)

    assert serialized[0]["loc"] == ["body", "file"]
    assert serialized[0]["ctx"]["error"] == "Expected UploadFile, received: <class 'str'>"


def test_serialize_validation_error_details_decodes_bytes():
    error_details = [{
        "type": "bytes_error",
        "loc": ("body", "payload"),
        "input": b"abc",
    }]

    serialized = serialize_validation_error_details(error_details)

    assert serialized[0]["input"] == "abc"
