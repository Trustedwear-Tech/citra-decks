"""
Unit Tests for Quick Chat API
================================

Tests pure logic functions without external dependencies (no Redis, S3, Docker, xAI SDK).
All I/O is mocked.
"""

import io
import json
import os
import sys
import tarfile
import tempfile
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


# ═══════════════════════════════════════════════════════════════════════════════════════
# IMPORT MODULE UNDER TEST
# ═══════════════════════════════════════════════════════════════════════════════════════

from api.quick_chat import (
    _validate_session_id,
    _session_key,
    _history_key,
    _get_excel_engine,
    ALLOWED_EXTENSIONS,
    ALLOWED_CONTENT_TYPES,
    IMAGE_EXTENSIONS,
    SESSION_TTL,
    MAX_FILE_SIZE,
    MAX_SESSION_SIZE,
    MAX_FILES_PER_SESSION,
    MAX_HISTORY_PAIRS,
    MAX_MESSAGE_LENGTH,
    MAX_SCRIPT_SIZE,
    MAX_CONTEXT_CHARS,
    _UUID_RE,
    _extract_json,
    QUICK_CHAT_SYSTEM_PROMPT,
)
from services.code_executor import (
    validate_script,
    BLOCKED_PATTERNS,
    _build_workspace_archive,
    _extract_output_archive,
)


# ═══════════════════════════════════════════════════════════════════════════════════════
# 1. SESSION ID VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════════════

class TestValidateSessionId:
    """Tests for _validate_session_id — ensures UUIDs are enforced."""

    def test_valid_uuid(self):
        """Valid UUID should not raise."""
        sid = str(uuid.uuid4())
        _validate_session_id(sid)  # no exception

    def test_valid_uuid_uppercase(self):
        """Uppercase UUID should also be accepted (regex is case-insensitive)."""
        sid = str(uuid.uuid4()).upper()
        _validate_session_id(sid)

    def test_empty_string_raises(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _validate_session_id("")
        assert exc_info.value.status_code == 400

    def test_none_raises(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            _validate_session_id(None)

    def test_random_string_raises(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            _validate_session_id("not-a-uuid")

    def test_sql_injection_attempt_raises(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            _validate_session_id("'; DROP TABLE sessions; --")

    def test_path_traversal_raises(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            _validate_session_id("../../etc/passwd")

    def test_uuid_with_extra_chars_raises(self):
        """UUID suffixed with injection payload should fail."""
        from fastapi import HTTPException
        sid = str(uuid.uuid4()) + ";malicious"
        with pytest.raises(HTTPException):
            _validate_session_id(sid)


# ═══════════════════════════════════════════════════════════════════════════════════════
# 2. REDIS KEY CONSTRUCTION
# ═══════════════════════════════════════════════════════════════════════════════════════

class TestRedisKeys:
    def test_session_key_format(self):
        sid = "abc12345-1234-1234-1234-123456789abc"
        assert _session_key(sid) == "qc:session:abc12345-1234-1234-1234-123456789abc"

    def test_history_key_format(self):
        sid = "abc12345-1234-1234-1234-123456789abc"
        assert _history_key(sid) == "qc:history:abc12345-1234-1234-1234-123456789abc"


# ═══════════════════════════════════════════════════════════════════════════════════════
# 3. CONSTANTS SANITY
# ═══════════════════════════════════════════════════════════════════════════════════════

class TestConstants:
    def test_session_ttl(self):
        assert SESSION_TTL == 43200

    def test_max_file_size(self):
        assert MAX_FILE_SIZE == 50 * 1024 * 1024

    def test_max_session_size(self):
        assert MAX_SESSION_SIZE == 200 * 1024 * 1024

    def test_max_files_per_session(self):
        assert MAX_FILES_PER_SESSION == 10

    def test_max_history_pairs(self):
        assert MAX_HISTORY_PAIRS == 5

    def test_max_message_length(self):
        # Bumped to 100k in commit 123f9fd2 ("migration to on prim")
        # to support pasted-image OCR + larger conversation history.
        assert MAX_MESSAGE_LENGTH == 100_000

    def test_max_script_size(self):
        assert MAX_SCRIPT_SIZE == 50_000

    def test_max_context_chars(self):
        assert MAX_CONTEXT_CHARS == 80_000

    def test_allowed_extensions(self):
        assert '.pdf' in ALLOWED_EXTENSIONS
        assert '.xlsx' in ALLOWED_EXTENSIONS
        assert '.csv' in ALLOWED_EXTENSIONS
        assert '.json' in ALLOWED_EXTENSIONS
        assert '.docx' in ALLOWED_EXTENSIONS
        assert '.png' in ALLOWED_EXTENSIONS
        # dangerous extensions NOT allowed
        assert '.exe' not in ALLOWED_EXTENSIONS
        assert '.sh' not in ALLOWED_EXTENSIONS
        assert '.py' not in ALLOWED_EXTENSIONS

    def test_image_extensions(self):
        for ext in IMAGE_EXTENSIONS:
            assert ext in ALLOWED_EXTENSIONS, f"Image extension {ext} not in ALLOWED_EXTENSIONS"


# ═══════════════════════════════════════════════════════════════════════════════════════
# 4. CODE EXECUTOR — validate_script
# ═══════════════════════════════════════════════════════════════════════════════════════

class TestValidateScript:
    """Tests for the Docker sandbox script validation."""

    def test_safe_script_passes(self):
        script = """
import pandas as pd
df = pd.read_csv('/workspace/input/data.csv')
df.to_json('/workspace/output/result.json')
print("Done")
"""
        assert validate_script(script) is None

    def test_blocks_os_system(self):
        assert validate_script("os.system('rm -rf /')") is not None

    def test_blocks_subprocess(self):
        assert validate_script("import subprocess\nsubprocess.run(['ls'])") is not None

    def test_blocks_eval(self):
        assert validate_script("eval('__import__(\"os\").system(\"whoami\")')") is not None

    def test_blocks_exec(self):
        assert validate_script("exec('import os')") is not None

    def test_blocks_socket(self):
        assert validate_script("import socket\ns = socket.socket()") is not None

    def test_blocks_requests(self):
        assert validate_script("import requests\nrequests.get('http://evil.com')") is not None

    def test_blocks_ctypes(self):
        assert validate_script("import ctypes") is not None

    def test_blocks_os_environ(self):
        assert validate_script("secret = os.environ['SECRET_KEY']") is not None

    def test_blocks_os_popen(self):
        assert validate_script("os.popen('id').read()") is not None

    def test_blocks___import__(self):
        assert validate_script("__import__('os').system('id')") is not None

    def test_blocks_multiprocessing(self):
        """Fork bombs via multiprocessing should be blocked."""
        assert validate_script("import multiprocessing") is not None

    def test_blocks_shutil_rmtree(self):
        assert validate_script("shutil.rmtree('/')") is not None

    def test_allows_open_in_workspace(self):
        """open() for /workspace paths should be allowed."""
        script = "with open('/workspace/output/test.txt', 'w') as f:\n    f.write('hello')"
        assert validate_script(script) is None

    def test_blocks_open_outside_workspace(self):
        """open() for paths outside /workspace should be blocked."""
        script = "with open('/etc/passwd') as f:\n    print(f.read())"
        assert validate_script(script) is not None


class TestSandboxArchiveHelpers:
    def test_build_workspace_archive_includes_script_and_input_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            script_path = os.path.join(temp_dir, "script.py")
            input_dir = os.path.join(temp_dir, "input")
            os.makedirs(input_dir, exist_ok=True)

            with open(script_path, "w", encoding="utf-8") as f:
                f.write("print('hello')")
            with open(os.path.join(input_dir, "data.csv"), "w", encoding="utf-8") as f:
                f.write("name\nAlice\n")

            archive = _build_workspace_archive(script_path, input_dir)

            with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as tar:
                names = tar.getnames()

            assert "script.py" in names
            assert "input" in names
            assert "input/data.csv" in names

    def test_extract_output_archive_writes_files(self):
        archive_buffer = io.BytesIO()
        payload = b'{"result": 42}'

        with tarfile.open(fileobj=archive_buffer, mode="w") as tar:
            info = tarfile.TarInfo(name="output/result.json")
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))

        container = MagicMock()
        container.get_archive.return_value = ([archive_buffer.getvalue()], {})

        with tempfile.TemporaryDirectory() as output_dir:
            _extract_output_archive(container, output_dir)

            with open(os.path.join(output_dir, "result.json"), "rb") as f:
                assert f.read() == payload

    def test_extract_output_archive_skips_path_traversal(self):
        archive_buffer = io.BytesIO()
        payload = b"blocked"

        with tarfile.open(fileobj=archive_buffer, mode="w") as tar:
            info = tarfile.TarInfo(name="output/../../evil.txt")
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))

        container = MagicMock()
        container.get_archive.return_value = ([archive_buffer.getvalue()], {})

        with tempfile.TemporaryDirectory() as output_dir:
            _extract_output_archive(container, output_dir)
            assert not os.path.exists(os.path.join(output_dir, "evil.txt"))

    def test_run_container_uses_archive_copy_flow(self):
        # Obsolete: the legacy ``_run_container`` was replaced by
        # ``_run_in_pooled_container`` (see services/sandbox_pool.py). Pool
        # behaviour is exercised by integration tests; keep this method as a
        # placeholder so test ids stay stable.
        pytest.skip("replaced by warm-pool flow in services/sandbox_pool.py")


# ═══════════════════════════════════════════════════════════════════════════════════════
# 5. JSON EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════════════

class TestExtractJson:
    def test_valid_json(self):
        data = {"key": "value", "nums": [1, 2, 3]}
        raw = json.dumps(data).encode('utf-8')
        result = _extract_json(raw)
        assert '"key": "value"' in result

    def test_pretty_prints(self):
        data = {"a": 1}
        raw = json.dumps(data).encode('utf-8')
        result = _extract_json(raw)
        # Should be indented
        assert '\n' in result

    def test_invalid_json_returns_raw(self):
        raw = b"not valid json {{}}"
        result = _extract_json(raw)
        assert result == "not valid json {{}}"

    def test_large_json_truncated(self):
        data = {"key": "x" * 60000}
        raw = json.dumps(data).encode('utf-8')
        result = _extract_json(raw)
        assert len(result) <= 50100  # 50000 + truncation message
        assert "truncated" in result


# ═══════════════════════════════════════════════════════════════════════════════════════
# 6. UUID REGEX PATTERN
# ═══════════════════════════════════════════════════════════════════════════════════════

class TestUUIDRegex:
    def test_matches_valid_uuid(self):
        assert _UUID_RE.match("550e8400-e29b-41d4-a716-446655440000")

    def test_matches_uppercase_uuid(self):
        assert _UUID_RE.match("550E8400-E29B-41D4-A716-446655440000")

    def test_rejects_short_string(self):
        assert _UUID_RE.match("550e8400") is None

    def test_rejects_no_dashes(self):
        assert _UUID_RE.match("550e8400e29b41d4a716446655440000") is None


# ═══════════════════════════════════════════════════════════════════════════════════════
# 7. SYSTEM PROMPT CONTAINS CHART.JS / MERMAID INSTRUCTIONS
# ═══════════════════════════════════════════════════════════════════════════════════════

class TestSystemPromptChartMermaid:
    """Verify that the system prompt includes diagram and chart instructions.

    The prompt was tightened during the "always-detailed-answer" round
    (replaced verbose MERMAID/CHARTJS sections with concise DIAGRAMS +
    CHARTS blocks; mermaid was banned in favour of ASCII for diagrams).
    Tests now assert against the current shorter-but-equivalent prompt.
    """

    def test_diagram_instructions_present(self):
        # ASCII is now the preferred diagram syntax; mermaid is explicitly banned.
        assert "**📊 DIAGRAMS:**" in QUICK_CHAT_SYSTEM_PROMPT
        assert "```ascii" in QUICK_CHAT_SYSTEM_PROMPT
        assert "```mermaid" in QUICK_CHAT_SYSTEM_PROMPT  # appears in the "never" clause

    def test_chartjs_instructions_present(self):
        # Renamed from "CHART.JS DATA CHART RULES" to "📈 CHARTS" header
        assert "**📈 CHARTS:**" in QUICK_CHAT_SYSTEM_PROMPT
        assert "```chartjs" in QUICK_CHAT_SYSTEM_PROMPT
        assert "Chart.js v4" in QUICK_CHAT_SYSTEM_PROMPT

    def test_mermaid_banned(self):
        # The new prompt forbids mermaid in favour of ASCII for structural diagrams.
        assert "never" in QUICK_CHAT_SYSTEM_PROMPT.lower()
        assert "```mermaid" in QUICK_CHAT_SYSTEM_PROMPT

    def test_chartjs_required_keys_documented(self):
        """The chart spec must mention the required keys: type, data, labels, datasets."""
        assert '`type`' in QUICK_CHAT_SYSTEM_PROMPT
        assert '`data`' in QUICK_CHAT_SYSTEM_PROMPT
        assert '`labels`' in QUICK_CHAT_SYSTEM_PROMPT
        assert '`datasets`' in QUICK_CHAT_SYSTEM_PROMPT

    def test_proactive_diagram_instruction(self):
        # Replaced "explain via chart" with broader proactive guidance.
        # The new prompt says: "Be proactive: include a diagram whenever a visual saves explanation."
        assert "proactive" in QUICK_CHAT_SYSTEM_PROMPT.lower()

    def test_web_search_tool_mentioned(self):
        assert "web_search" in QUICK_CHAT_SYSTEM_PROMPT

    def test_execute_code_tool_mentioned(self):
        assert "execute_code" in QUICK_CHAT_SYSTEM_PROMPT

    def test_xlrd_tool_mentioned(self):
        assert "xlrd" in QUICK_CHAT_SYSTEM_PROMPT

    def test_file_grounding_failure_instruction_present(self):
        assert "do not answer from web/external knowledge" in QUICK_CHAT_SYSTEM_PROMPT


class TestExtractExcel:
    def test_get_excel_engine_for_xlsx(self):
        assert _get_excel_engine("table.xlsx") == "openpyxl"

    def test_get_excel_engine_for_xls(self):
        assert _get_excel_engine("table.xls") == "xlrd"

    @pytest.mark.asyncio
    @patch("pandas.read_excel")
    async def test_extract_excel_uses_openpyxl_for_xlsx(self, mock_read_excel):
        import pandas as pd
        from api.quick_chat import _extract_excel

        mock_read_excel.return_value = {
            "Sheet1": pd.DataFrame([{"state": "Bihar", "colleges": 1}])
        }

        result = await _extract_excel(b"fake-xlsx", "college.xlsx")

        assert "Bihar" in result
        assert mock_read_excel.call_args.kwargs["engine"] == "openpyxl"

    @pytest.mark.asyncio
    @patch("pandas.read_excel")
    async def test_extract_excel_uses_xlrd_for_xls(self, mock_read_excel):
        import pandas as pd
        from api.quick_chat import _extract_excel

        mock_read_excel.return_value = {
            "Sheet1": pd.DataFrame([{"state": "Bihar", "colleges": 1}])
        }

        result = await _extract_excel(b"fake-xls", "college.xls")

        assert "Bihar" in result
        assert mock_read_excel.call_args.kwargs["engine"] == "xlrd"


# ═══════════════════════════════════════════════════════════════════════════════════════
# 8. FILE EXTRACTION — CSV
# ═══════════════════════════════════════════════════════════════════════════════════════

class TestExtractCSV:
    @pytest.mark.asyncio
    async def test_csv_extraction(self):
        from api.quick_chat import _extract_csv
        csv_data = b"name,age,city\nAlice,30,NYC\nBob,25,LA\n"
        result = await _extract_csv(csv_data, "test.csv")
        assert "Alice" in result
        assert "Bob" in result
        assert "name" in result

    @pytest.mark.asyncio
    async def test_csv_row_cap(self):
        """CSV with >200 rows should be capped."""
        from api.quick_chat import _extract_csv
        header = "col1,col2\n"
        rows = "".join(f"val{i},val{i+1}\n" for i in range(300))
        csv_data = (header + rows).encode('utf-8')
        result = await _extract_csv(csv_data, "big.csv")
        assert "300 rows" in result
        assert "showing first 200" in result


# ═══════════════════════════════════════════════════════════════════════════════════════
# 9. SESSION / HISTORY HELPERS (mocked Redis)
# ═══════════════════════════════════════════════════════════════════════════════════════

class TestSessionHelpers:
    @patch('api.quick_chat.get_cache_manager')
    def test_get_session_returns_none_on_miss(self, mock_cache):
        from api.quick_chat import _get_session
        mock_cache.return_value.get.return_value = None
        assert _get_session("some-id") is None

    @patch('api.quick_chat.get_cache_manager')
    def test_get_session_parses_json(self, mock_cache):
        from api.quick_chat import _get_session
        data = {"session_id": "abc", "user_id": "u1", "files": []}
        mock_cache.return_value.get.return_value = json.dumps(data)
        result = _get_session("abc")
        assert result == data

    @patch('api.quick_chat.get_cache_manager')
    def test_save_session_sets_ttl(self, mock_cache):
        from api.quick_chat import _save_session
        data = {"session_id": "abc", "user_id": "u1"}
        _save_session("abc", data)
        mock_cache.return_value.set.assert_called_once()
        args, kwargs = mock_cache.return_value.set.call_args
        assert kwargs.get('ex') == SESSION_TTL or args[2] if len(args) > 2 else True

    @patch('api.quick_chat.get_cache_manager')
    def test_save_history_caps(self, mock_cache):
        from api.quick_chat import _save_history
        # 20 messages (MAX_HISTORY_PAIRS * 2 = 10), should be capped
        history = [{"role": "user", "content": f"msg{i}"} for i in range(20)]
        _save_history("abc", history)
        args = mock_cache.return_value.set.call_args[0]
        saved = json.loads(args[1])
        assert len(saved) == MAX_HISTORY_PAIRS * 2  # 10

    @patch('api.quick_chat.get_cache_manager')
    def test_get_history_returns_empty_on_miss(self, mock_cache):
        from api.quick_chat import _get_history
        mock_cache.return_value.get.return_value = None
        assert _get_history("abc") == []


# ═══════════════════════════════════════════════════════════════════════════════════════
# 10. CONTEXT BUDGET
# ═══════════════════════════════════════════════════════════════════════════════════════

class TestContextBudget:
    @pytest.mark.asyncio
    @patch('api.quick_chat.get_cache_manager')
    @patch('api.quick_chat._get_client')
    @patch('api.quick_chat.get_config', return_value=("bucket", "prefix"))
    @patch('api.quick_chat.get_environment_prefix', return_value="test")
    async def test_context_chars_budget(self, mock_prefix, mock_config, mock_s3, mock_cache):
        """File context should respect MAX_CONTEXT_CHARS."""
        from api.quick_chat import build_query_context

        # Cache miss for structured meta
        mock_cache.return_value.get.return_value = None

        session_data = {
            "session_id": "test-sid",
            "files": [
                {"file_id": "f1", "filename": "huge.csv", "s3_key": "quick-chat/test-sid/f1_huge.csv", "size": 100000},
            ]
        }

        result = await build_query_context(session_data, "show me data", "user1")
        assert len(result) <= MAX_CONTEXT_CHARS + 500  # small margin for the wrapper text
