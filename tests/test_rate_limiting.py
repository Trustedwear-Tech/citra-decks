# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

import os
import os
import pytest
from fastapi.testclient import TestClient
from fastapi import Request
from main import app
from slowapi import Limiter
from slowapi.util import get_remote_address
import main

# Mock startup services to avoid connecting to real DBs/Milvus/etc during test
async def mock_startup():
    pass
    
async def mock_shutdown():
    pass

main.startup_services = mock_startup
main.shutdown_services = mock_shutdown

# Force in-memory storage for testing to avoid Redis dependency
os.environ["REDIS_CACHE_ENABLED"] = "false"
# Disable auth verification to test rate limits in isolation
os.environ["DISABLE_AUTH"] = "true"

# Re-initialize limiter with memory storage for tests
from middleware.rate_limit_middleware import limiter
limiter.storage_uri = "memory://"
limiter._storage = None # Reset internal storage to force re-init

# Add dummy auth header to bypass middleware check (which requires header presence)
client = TestClient(app)
AUTH_HEADERS = {"Authorization": "Bearer dummy_token"}

def test_rate_limit_standard():
    """
    Test that the standard rate limit (default 100/minute) works.
    We will override it for this test to a small number.
    """
    # Override the default limit for a specific test route
    # We can't easily override the global limit on the already running app without reloading
    # intricate parts. Instead, let's test a dummy endpoint with a strict limit.
    
    @app.get("/test_rate_limit")
    @limiter.limit("5/minute")
    def test_route(request: Request):
        return {"message": "ok"}
    
    # Hit the endpoint 5 times (should be OK)
    for _ in range(5):
        response = client.get("/test_rate_limit", headers=AUTH_HEADERS)
        assert response.status_code == 200
        
    # The 6th time should fail
    response = client.get("/test_rate_limit", headers=AUTH_HEADERS)
    assert response.status_code == 429
    assert "Too Many Requests" in response.text

def test_rate_limit_headers():
    """
    Test that X-RateLimit headers are present.
    """
    @app.get("/test_headers")
    @limiter.limit("5/minute")
    def test_headers_route(request: Request):
        return {"data": "ok"}
        
    response = client.get("/test_headers", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert "X-RateLimit-Limit" in response.headers
    assert "X-RateLimit-Remaining" in response.headers
