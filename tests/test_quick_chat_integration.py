"""
Integration Tests for Quick Chat API
======================================

Tests the full API flow through FastAPI TestClient with:
- Real Redis (via fakeredis) for session/history storage
- Mocked S3 (upload/download)
- Mocked auth (skips JWT verification)
- Real Docker sandbox execution (requires Docker Desktop + quick-chat-sandbox image)

Prerequisites:
  1. Docker Desktop running
  2. Build sandbox image ONCE:
       docker build -t quick-chat-sandbox -f Dockerfile.quick-chat-sandbox .
  3. pip install pytest pytest-asyncio fakeredis httpx
"""

import asyncio
import io
import json
import os
import sys
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# FIXTURES
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

TEST_USER_ID = "testuser@example.com"

# Create a single fake-redis instance shared across all tests
_fake_redis = fakeredis.FakeStrictRedis(decode_responses=True)


class FakeCacheManager:
    """Minimal wrapper around fakeredis matching CacheManager interface used by quick_chat."""

    def get(self, key):
        return _fake_redis.get(key)

    def set(self, key, value, ex=None):
        if ex:
            _fake_redis.setex(key, ex, value)
        else:
            _fake_redis.set(key, value)

    def delete(self, key):
        _fake_redis.delete(key)

    def _execute(self, cmd, *args, **kwargs):
        return getattr(_fake_redis, cmd)(*args, **kwargs)


_fake_cache = FakeCacheManager()


def _mock_get_secure_user_id():
    """Override FastAPI Depends(get_secure_user_id) to return test user."""
    return TEST_USER_ID


# Track uploaded S3 objects in-memory
_s3_store: dict = {}


def _mock_upload_file_to_s3(content, s3_key, content_type="application/octet-stream"):
    _s3_store[s3_key] = {"content": content, "content_type": content_type}


def _mock_generate_presigned_url(s3_key, expiry_seconds=1800):
    return f"https://fake-s3.example.com/{s3_key}?expires={expiry_seconds}"


def _mock_delete_file_from_s3(s3_key):
    _s3_store.pop(s3_key, None)


def _mock_list_objects_with_prefix(prefix, max_keys=500):
    return [k for k in _s3_store if k.startswith(prefix)]


def _mock_get_client():
    """Return a bucket client mock that can stream files from _s3_store."""
    client = MagicMock()

    def get_object(Bucket, Key):
        # Strip env prefix for lookup
        for stored_key in _s3_store:
            if Key.endswith(stored_key) or stored_key.endswith(Key.split("/", 1)[-1] if "/" in Key else Key):
                body = MagicMock()
                body.read.return_value = _s3_store[stored_key]["content"]
                return {"Body": body}
        # Fallback: try exact match with prefix stripped
        for stored_key, data in _s3_store.items():
            if stored_key in Key or Key in stored_key:
                body = MagicMock()
                body.read.return_value = data["content"]
                return {"Body": body}
        raise Exception(f"S3 key not found: {Key}")

    client.get_object = get_object
    return client


@pytest.fixture(autouse=True)
def _clean_state():
    """Reset fake redis and S3 store before each test."""
    _fake_redis.flushall()
    _s3_store.clear()
    yield
    _fake_redis.flushall()
    _s3_store.clear()


@pytest.fixture
def app():
    """Create and configure the FastAPI app with mocked dependencies."""
    # Patch before importing main, so the router picks up our mocks
    with patch("api.quick_chat.get_cache_manager", return_value=_fake_cache), \
         patch("api.quick_chat.upload_file", side_effect=_mock_upload_file_to_s3), \
         patch("api.quick_chat.generate_download_url", side_effect=_mock_generate_presigned_url), \
         patch("api.quick_chat.delete_file", side_effect=_mock_delete_file_from_s3), \
         patch("api.quick_chat.list_objects_with_prefix", side_effect=_mock_list_objects_with_prefix), \
         patch("api.quick_chat._get_client", side_effect=_mock_get_client), \
         patch("api.quick_chat.get_config", return_value=("test-bucket", "test-prefix")), \
         patch("api.quick_chat.get_environment_prefix", return_value="test"):

        from fastapi import FastAPI
        from api.quick_chat import router
        from auth_middleware import get_secure_user_id

        test_app = FastAPI()
        test_app.include_router(router)

        # Override auth dependency
        test_app.dependency_overrides[get_secure_user_id] = _mock_get_secure_user_id

        yield test_app


@pytest_asyncio.fixture
async def client(app):
    """Async HTTP client bound to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# HELPER
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async def create_session(client: AsyncClient) -> str:
    resp = await client.post("/quick-chat/session")
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    return data["session_id"]


async def upload_csv(client: AsyncClient, session_id: str, filename: str = "data.csv",
                     csv_content: bytes = b"name,age\nAlice,30\nBob,25\n") -> dict:
    resp = await client.post(
        "/quick-chat/upload",
        data={"session_id": session_id},
        files={"file": (filename, io.BytesIO(csv_content), "text/csv")},
    )
    assert resp.status_code == 200
    return resp.json()


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 1. SESSION LIFECYCLE
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestSessionLifecycle:
    @pytest.mark.asyncio
    async def test_create_session(self, client):
        sid = await create_session(client)
        assert len(sid) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_get_session_info(self, client):
        sid = await create_session(client)
        resp = await client.get(f"/quick-chat/session/{sid}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == sid
        assert body["files_count"] == 0

    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self, client):
        fake_sid = str(uuid.uuid4())
        resp = await client.get(f"/quick-chat/session/{fake_sid}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_session(self, client):
        sid = await create_session(client)
        resp = await client.delete(f"/quick-chat/session/{sid}")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # Session should be gone now
        resp2 = await client.get(f"/quick-chat/session/{sid}")
        assert resp2.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_session_id_format(self, client):
        resp = await client.get("/quick-chat/session/not-a-uuid")
        assert resp.status_code == 400


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 2. FILE UPLOAD
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestFileUpload:
    @pytest.mark.asyncio
    async def test_upload_csv(self, client):
        sid = await create_session(client)
        result = await upload_csv(client, sid)
        assert result["filename"] == "data.csv"
        assert result["files_count"] == 1
        assert result["size"] > 0

    @pytest.mark.asyncio
    async def test_upload_multiple_files(self, client):
        sid = await create_session(client)
        await upload_csv(client, sid, "file1.csv", b"a,b\n1,2\n")
        result = await upload_csv(client, sid, "file2.csv", b"x,y\n3,4\n")
        assert result["files_count"] == 2

    @pytest.mark.asyncio
    async def test_upload_disallowed_extension(self, client):
        sid = await create_session(client)
        resp = await client.post(
            "/quick-chat/upload",
            data={"session_id": sid},
            files={"file": ("malicious.exe", io.BytesIO(b"MZ..."), "application/x-msdownload")},
        )
        assert resp.status_code == 400
        assert "not supported" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_to_expired_session(self, client):
        fake_sid = str(uuid.uuid4())
        resp = await client.post(
            "/quick-chat/upload",
            data={"session_id": fake_sid},
            files={"file": ("test.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_too_many_files(self, client):
        sid = await create_session(client)
        for i in range(10):
            await upload_csv(client, sid, f"file{i}.csv", b"a,b\n1,2\n")

        # 11th file should be rejected
        resp = await client.post(
            "/quick-chat/upload",
            data={"session_id": sid},
            files={"file": ("file10.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
        )
        assert resp.status_code == 400
        assert "Maximum" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_json_file(self, client):
        sid = await create_session(client)
        json_data = json.dumps({"users": [{"name": "Alice"}, {"name": "Bob"}]}).encode()
        resp = await client.post(
            "/quick-chat/upload",
            data={"session_id": sid},
            files={"file": ("data.json", io.BytesIO(json_data), "application/json")},
        )
        assert resp.status_code == 200
        assert resp.json()["filename"] == "data.json"

    @pytest.mark.asyncio
    async def test_upload_rejects_string_file_field(self, client):
        sid = await create_session(client)
        resp = await client.post(
            "/quick-chat/upload",
            data={"session_id": sid, "file": "[object Object]"},
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert any(item["loc"][-1] == "file" for item in detail)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 3. FILE DELETE
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestFileDelete:
    @pytest.mark.asyncio
    async def test_delete_file(self, client):
        sid = await create_session(client)
        upload_result = await upload_csv(client, sid)
        file_id = upload_result["file_id"]

        resp = await client.delete(f"/quick-chat/file/{file_id}?session_id={sid}")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # Verify file is gone from session
        info = await client.get(f"/quick-chat/session/{sid}")
        assert info.json()["files_count"] == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_file(self, client):
        sid = await create_session(client)
        resp = await client.delete(f"/quick-chat/file/noexist?session_id={sid}")
        assert resp.status_code == 404


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 4. QUERY VALIDATION
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestQueryValidation:
    @pytest.mark.asyncio
    async def test_missing_session_id(self, client):
        resp = await client.post(
            "/quick-chat/query/stream",
            json={"message": "hello"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_message(self, client):
        sid = await create_session(client)
        resp = await client.post(
            "/quick-chat/query/stream",
            json={"session_id": sid, "message": ""},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_message_too_long(self, client):
        sid = await create_session(client)
        long_msg = "x" * 9000
        resp = await client.post(
            "/quick-chat/query/stream",
            json={"session_id": sid, "message": long_msg},
        )
        assert resp.status_code == 400
        assert "too long" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_invalid_session_for_query(self, client):
        fake_sid = str(uuid.uuid4())
        resp = await client.post(
            "/quick-chat/query/stream",
            json={"session_id": fake_sid, "message": "hi"},
        )
        assert resp.status_code == 404


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 5. AUTH / OWNERSHIP
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestOwnershipEnforcement:
    @pytest.mark.asyncio
    async def test_other_user_cannot_access_session(self, app, client):
        """A session created by user A should be 403 for user B."""
        from auth_middleware import get_secure_user_id

        # Create session as user A (default test user)
        sid = await create_session(client)

        # Now switch to user B
        app.dependency_overrides[get_secure_user_id] = lambda: "otheruser@example.com"

        resp = await client.get(f"/quick-chat/session/{sid}")
        assert resp.status_code == 403

        # Switch back
        app.dependency_overrides[get_secure_user_id] = _mock_get_secure_user_id

    @pytest.mark.asyncio
    async def test_other_user_cannot_upload(self, app, client):
        from auth_middleware import get_secure_user_id

        sid = await create_session(client)
        app.dependency_overrides[get_secure_user_id] = lambda: "attacker@evil.com"

        resp = await client.post(
            "/quick-chat/upload",
            data={"session_id": sid},
            files={"file": ("payload.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
        )
        assert resp.status_code == 403
        app.dependency_overrides[get_secure_user_id] = _mock_get_secure_user_id

    @pytest.mark.asyncio
    async def test_other_user_cannot_delete_session(self, app, client):
        from auth_middleware import get_secure_user_id

        sid = await create_session(client)
        app.dependency_overrides[get_secure_user_id] = lambda: "attacker@evil.com"

        resp = await client.delete(f"/quick-chat/session/{sid}")
        assert resp.status_code == 403
        app.dependency_overrides[get_secure_user_id] = _mock_get_secure_user_id


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 6. DOCKER SANDBOX INTEGRATION (requires Docker Desktop)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def _docker_available():
    try:
        import docker
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


def _sandbox_image_exists():
    try:
        import docker
        client = docker.from_env()
        client.images.get("quick-chat-sandbox")
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not _docker_available(),
    reason="Docker Desktop not running"
)
@pytest.mark.skipif(
    not _sandbox_image_exists(),
    reason="quick-chat-sandbox image not built (run: docker build -t quick-chat-sandbox -f Dockerfile.quick-chat-sandbox .)"
)
class TestDockerSandbox:
    """Integration tests that run real Docker containers."""

    @pytest.mark.asyncio
    async def test_simple_script_execution(self):
        """Run a simple print script in the sandbox."""
        from services.code_executor import execute_code

        with patch("services.code_executor._get_client"), \
             patch("services.code_executor.get_config", return_value=("bucket", "prefix")), \
             patch("services.code_executor.get_environment_prefix", return_value="test"), \
             patch("services.code_executor.upload_file", side_effect=_mock_upload_file_to_s3), \
             patch("services.code_executor.generate_download_url", side_effect=_mock_generate_presigned_url):

            result = await execute_code(
                script='print("Hello from sandbox!")',
                session_id="test-session",
                files=[],
                output_filename="output.txt",
            )

            assert result["success"] is True
            assert "Hello from sandbox!" in result["stdout"]

    @pytest.mark.asyncio
    async def test_script_writes_output_file(self):
        """Script that creates an output file."""
        from services.code_executor import execute_code

        with patch("services.code_executor._get_client"), \
             patch("services.code_executor.get_config", return_value=("bucket", "prefix")), \
             patch("services.code_executor.get_environment_prefix", return_value="test"), \
             patch("services.code_executor.upload_file", side_effect=_mock_upload_file_to_s3), \
             patch("services.code_executor.generate_download_url", side_effect=_mock_generate_presigned_url):

            script = """
import json
data = {"result": [1, 2, 3]}
with open('/workspace/output/result.json', 'w') as f:
    json.dump(data, f)
print("Wrote result.json")
"""
            result = await execute_code(
                script=script,
                session_id="test-session",
                files=[],
                output_filename="result.json",
            )

            assert result["success"] is True
            assert "Wrote result.json" in result["stdout"]
            assert len(result["output_files"]) == 1
            assert result["output_files"][0]["filename"] == "result.json"

    @pytest.mark.asyncio
    async def test_script_with_pandas(self):
        """Script that uses pandas (pre-installed in sandbox image)."""
        from services.code_executor import execute_code

        with patch("services.code_executor._get_client"), \
             patch("services.code_executor.get_config", return_value=("bucket", "prefix")), \
             patch("services.code_executor.get_environment_prefix", return_value="test"), \
             patch("services.code_executor.upload_file", side_effect=_mock_upload_file_to_s3), \
             patch("services.code_executor.generate_download_url", side_effect=_mock_generate_presigned_url):

            script = """
import pandas as pd
df = pd.DataFrame({"name": ["Alice", "Bob"], "age": [30, 25]})
df.to_csv('/workspace/output/people.csv', index=False)
print(f"Wrote {len(df)} rows")
"""
            result = await execute_code(
                script=script,
                session_id="test-session",
                files=[],
                output_filename="people.csv",
            )

            assert result["success"] is True
            assert "2 rows" in result["stdout"]

    @pytest.mark.asyncio
    async def test_script_error_returns_stderr(self):
        """Script with intentional error should return stderr."""
        from services.code_executor import execute_code

        with patch("services.code_executor._get_client"), \
             patch("services.code_executor.get_config", return_value=("bucket", "prefix")), \
             patch("services.code_executor.get_environment_prefix", return_value="test"), \
             patch("services.code_executor.upload_file", side_effect=_mock_upload_file_to_s3), \
             patch("services.code_executor.generate_download_url", side_effect=_mock_generate_presigned_url):

            result = await execute_code(
                script='raise ValueError("intentional test error")',
                session_id="test-session",
                files=[],
                output_filename="output.txt",
            )

            assert result["success"] is False
            assert "ValueError" in result["stderr"]

    @pytest.mark.asyncio
    async def test_blocked_script_rejected(self):
        """Scripts with blocked patterns should not even reach Docker."""
        from services.code_executor import execute_code

        with patch("services.code_executor._get_client"), \
             patch("services.code_executor.get_config", return_value=("bucket", "prefix")), \
             patch("services.code_executor.get_environment_prefix", return_value="test"), \
             patch("services.code_executor.upload_file"), \
             patch("services.code_executor.generate_download_url"):

            result = await execute_code(
                script='import subprocess\nsubprocess.run(["ls"])',
                session_id="test-session",
                files=[],
                output_filename="output.txt",
            )

            assert result["success"] is False
            assert "blocked" in result["stderr"].lower() or "validation failed" in result["stderr"].lower()

    @pytest.mark.asyncio
    async def test_sandbox_has_no_network(self):
        """Container should not have network access."""
        from services.code_executor import execute_code

        with patch("services.code_executor._get_client"), \
             patch("services.code_executor.get_config", return_value=("bucket", "prefix")), \
             patch("services.code_executor.get_environment_prefix", return_value="test"), \
             patch("services.code_executor.upload_file", side_effect=_mock_upload_file_to_s3), \
             patch("services.code_executor.generate_download_url", side_effect=_mock_generate_presigned_url):

            # This uses urllib which is not in BLOCKED_PATTERNS but network is disabled
            # We test with a plain socket approach via error detection
            script = """
import urllib.request
try:
    urllib.request.urlopen("http://8.8.8.8", timeout=3)
    print("NETWORK_ACCESSIBLE")
except Exception as e:
    print(f"NETWORK_BLOCKED: {e}")
"""
            # Note: urllib is blocked by validate_script, so this tests the validation layer
            result = await execute_code(
                script=script,
                session_id="test-session",
                files=[],
                output_filename="output.txt",
            )

            # urllib is in BLOCKED_PATTERNS, so it should fail validation
            assert result["success"] is False


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 7. FULL FLOW â€” CREATE â†’ UPLOAD â†’ QUERY (mocked LLM)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestFullFlowMockedLLM:
    """End-to-end flow with mocked xAI SDK to test the plumbing."""

    @pytest.mark.asyncio
    async def test_full_flow_session_upload_query(self, client):
        """Create session â†’ upload file â†’ send query (with mocked LLM response)."""
        from streaming_response import StreamEvent, StreamEventType

        sid = await create_session(client)
        await upload_csv(client, sid)

        # Mock run_agentic_query to yield a simple response
        async def fake_agentic_query(*args, **kwargs):
            yield StreamEvent(StreamEventType.CHUNK, {"text": "Based on the CSV data, "})
            yield StreamEvent(StreamEventType.CHUNK, {"text": "Alice is 30 and Bob is 25."})
            yield StreamEvent(StreamEventType.USAGE, {
                "input_tokens": 100, "output_tokens": 20,
                "cached_tokens": 0, "internet_grounding_cost": 0.0,
                "processing_time": 0.5,
            })
            yield StreamEvent(StreamEventType.DONE, {"processing_time": 0.5, "output_files_count": 0})

        with patch("api.quick_chat.run_agentic_query", side_effect=fake_agentic_query), \
             patch("api.quick_chat.build_query_context", new_callable=AsyncMock, return_value="name,age\nAlice,30\nBob,25"):

            resp = await client.post(
                "/quick-chat/query/stream",
                json={"session_id": sid, "message": "Who is older?"},
            )
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")

            # Parse SSE events
            body = resp.text
            assert "Alice is 30" in body
            assert "event: chunk" in body
            assert "event: done" in body

    @pytest.mark.asyncio
    async def test_query_with_chart_response(self, client):
        """Verify the SSE stream can carry chart.js / mermaid content through."""
        from streaming_response import StreamEvent, StreamEventType

        sid = await create_session(client)

        chart_response = """Here's a chart of the data:

```chartjs
{
  "type": "bar",
  "data": {
    "labels": ["Alice", "Bob"],
    "datasets": [{"label": "Age", "data": [30, 25]}]
  }
}
```

And a flow diagram:

```mermaid
graph TD
    A[Start] --> B[Process Data]
    B --> C[Generate Chart]
    C --> D[finish]
```
"""

        async def fake_agentic_query(*args, **kwargs):
            yield StreamEvent(StreamEventType.CHUNK, {"text": chart_response})
            yield StreamEvent(StreamEventType.DONE, {"processing_time": 0.5, "output_files_count": 0})

        with patch("api.quick_chat.run_agentic_query", side_effect=fake_agentic_query), \
             patch("api.quick_chat.build_query_context", new_callable=AsyncMock, return_value=""):

            resp = await client.post(
                "/quick-chat/query/stream",
                json={"session_id": sid, "message": "Show me a chart and diagram"},
            )
            assert resp.status_code == 200
            body = resp.text
            # The SSE stream should contain the chart and mermaid blocks
            # Note: content is JSON-encoded inside SSE data field, so quotes are escaped
            assert "chartjs" in body
            assert "mermaid" in body
            assert "bar" in body

    @pytest.mark.asyncio
    async def test_conversation_history_saved(self, client):
        """After a query, history should be saved in Redis."""
        from streaming_response import StreamEvent, StreamEventType

        sid = await create_session(client)

        async def fake_agentic_query(*args, **kwargs):
            yield StreamEvent(StreamEventType.CHUNK, {"text": "Response text."})
            yield StreamEvent(StreamEventType.DONE, {"processing_time": 0.1, "output_files_count": 0})

        with patch("api.quick_chat.run_agentic_query", side_effect=fake_agentic_query), \
             patch("api.quick_chat.build_query_context", new_callable=AsyncMock, return_value=""):

            await client.post(
                "/quick-chat/query/stream",
                json={"session_id": sid, "message": "Hello there"},
            )

        # Check Redis for history
        from api.quick_chat import _get_history
        with patch("api.quick_chat.get_cache_manager", return_value=_fake_cache):
            history = _get_history(sid)
            assert len(history) == 2  # user + assistant
            assert history[0]["role"] == "user"
            assert history[0]["content"] == "Hello there"
            assert history[1]["role"] == "assistant"
            assert "Response text" in history[1]["content"]


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 8. DOWNLOAD ENDPOINT
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestDownload:
    @pytest.mark.asyncio
    async def test_download_uploaded_file(self, client):
        sid = await create_session(client)
        result = await upload_csv(client, sid)
        file_id = result["file_id"]

        resp = await client.get(f"/quick-chat/download/{file_id}?session_id={sid}")
        assert resp.status_code == 200
        body = resp.json()
        assert "download_url" in body
        assert "fake-s3.example.com" in body["download_url"]

    @pytest.mark.asyncio
    async def test_download_invalid_file_id(self, client):
        sid = await create_session(client)
        resp = await client.get(f"/quick-chat/download/a..b?session_id={sid}")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_download_nonexistent_file(self, client):
        """A file_id not in session files falls through to output-path presigned URL.
        S3 presigned URLs are generated client-side, so the endpoint returns 200
        even if the actual S3 object doesn't exist."""
        sid = await create_session(client)
        resp = await client.get(f"/quick-chat/download/nofile?session_id={sid}")
        # generate_presigned_url doesn't verify S3 object existence
        assert resp.status_code == 200
        assert "download_url" in resp.json()
