# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
from dataclasses import dataclass
import json
import os

# Define a mock ClassificationResult matching the one in services.parallel_classifier
@dataclass
class MockClassificationResult:
    intent: str = "edit"
    action_type: str = "edit_text"
    scope: str = "full"
    confidence: float = 0.8
    resolved_scope: str = "slide"
    scope_message: str = ""
    requires_data: bool = True
    requires_vault: bool = True
    requires_image: bool = False
    ai_message: str = ""
    clarification_needed: str = None
    chart_type: str = None
    chart_query: str = None
    create_topic: str = None

@pytest.fixture
def client_fixture():
    from main import app
    return TestClient(app)

# Test constants
TEST_USER_ID = "test_user_123"
TEST_PAGE_ID = "page_test_001"
TEST_FOLDER_IDS = ["folder_1", "folder_2"]

@pytest.fixture
def mock_auth_bypass():
    """Environment setup for auth bypass."""
    # Ensure DISABLE_AUTH is set for bypass
    with patch.dict(os.environ, {"DISABLE_AUTH": "true"}):
        yield

@pytest.fixture
def mock_classifier():
    """Mock the parallel classifier."""
    with patch('services.parallel_classifier.classify_report_edit', new_callable=AsyncMock) as mock:
        yield mock

@pytest.fixture
def mock_llm_call():
    """Mock LLM text generation."""
    with patch('composer_context.llm_call') as mock:
        yield mock

@pytest.fixture
def mock_vault_context():
    """Mock vault context retrieval. After the agentic-tool refactor the
    /composer/ai-edit endpoint no longer calls retrieve_vault_context — it
    routes through services.enterprise_tools.run_Enterprise_or_Personal_tool when
    requires_vault=True and folder_ids are present. We mock both the legacy
    path (for back-compat assertions like assert_not_called) AND the new
    agentic path (so the endpoint can complete without hitting a real LLM).
    """
    with patch('composer_context.retrieve_vault_context') as mock_legacy, \
         patch('services.enterprise_tools.run_Enterprise_or_Personal_tool', new_callable=AsyncMock) as mock_agentic:
        mock_legacy.return_value = "Mock vault content: details about the project."
        mock_agentic.return_value = "<h1>Expanded Content</h1><p>With vault data [vault:doc_abc]</p>"
        # Expose both on the same fixture object so tests can inspect either
        mock_legacy.agentic = mock_agentic
        yield mock_legacy


class TestReportEditIntelligent:
    """
    Intelligent test suite for Report Edit API (/composer/ai-edit).
    Verifies intent logic, prompt compliance, and frontend contract.
    """

    def test_report_greeting_intent(self, client_fixture, mock_auth_bypass, mock_classifier):
        """Verify 'hi' returns 'message_only' action type without valid token."""
        
        # Simulate Classifier response
        mock_classifier.return_value = MockClassificationResult(
            intent="greeting",
            action_type="greeting",
            ai_message="Hello there!",
            requires_data=False,
            requires_vault=False
        )
        
        payload = {
            "instruction": "hi",
            "current_content": "",
            "page_id": TEST_PAGE_ID,
            "user_id": TEST_USER_ID
        }
        
        # Call with dummy token to trigger bypass logic
        response = client_fixture.post("/composer/ai-edit", json=payload, headers={"Authorization": "Bearer dummy"})
        data = response.json()
        
        assert response.status_code == 200
        assert data["success"] is True
        assert data["action_type"] == "message_only"
        assert data["ai_message"] == "Hello there!"

    def test_report_create_new_page(self, client_fixture, mock_auth_bypass, mock_classifier, mock_llm_call):
        """Verify 'create new page' intent returns 'create_new' action."""
        
        # 1. Mock Classifier response
        mock_classifier.return_value = MockClassificationResult(
            intent="create_new",
            action_type="create_new",
            create_topic="Project Plan",
            ai_message="Creating page...",
            requires_data=True,
            requires_vault=True
        )
        
        # 2. Mock Content Generator response (LLM) - Create New uses LLM
        mock_llm_call.return_value = json.dumps({
            "new_title": "Project Plan",
            "new_content": "<h1>Project Plan</h1><p>Details...</p>",
            "ai_message": "Created page."
        })
        
        payload = {
            "instruction": "Create a new page about Project Plan",
            "current_content": "",
            "page_id": TEST_PAGE_ID,
            "user_id": TEST_USER_ID
        }
        
        response = client_fixture.post("/composer/ai-edit", json=payload, headers={"Authorization": "Bearer dummy"})
        data = response.json()
        
        assert data["success"] is True
        assert data["action_type"] == "create_new"
        assert data["new_title"] == "Project Plan"
        assert "<h1>Project Plan</h1>" in data["new_content"]

    @pytest.mark.xfail(
        reason="Asserts a Stage1/Stage2 multi-LLM-call pattern (with "
        "`needs_vault_data` JSON envelope) that no longer exists. The "
        "agentic-tool refactor collapsed ai-edit into a single LLM call "
        "that returns raw HTML. Test needs rewriting against the new shape."
    )
    def test_report_quick_edit_stage1(self, client_fixture, mock_auth_bypass, mock_classifier, mock_llm_call, mock_vault_context):
        """
        Verify 'simple edit' intent (Stage 1) returns 'edit' action
        without calling vault retrieval.
        """
        
        # 1. Mock Classifier: "edit"
        mock_classifier.return_value = MockClassificationResult(
            intent="edit",
            action_type="edit_text",
            ai_message="Editing text...",
            requires_data=False, # Classifier thinks simple
            requires_vault=False
        )
        
        # 2. Mock Stage 1 Assessment: needs_vault_data = False (Direct edit)
        mock_llm_call.return_value = json.dumps({
            "needs_vault_data": False,
            "edited_content": "<p>Fixed content</p>",
            "reason": "Simple grammar fix"
        })
        
        payload = {
            "instruction": "Fix typos",
            "current_content": "<p>Fixxed content</p>",
            "page_id": TEST_PAGE_ID,
            "user_id": TEST_USER_ID,
            "edit_mode": "overall"
        }
        
        response = client_fixture.post("/composer/ai-edit", json=payload, headers={"Authorization": "Bearer dummy"})
        data = response.json()
        
        assert data["success"] is True
        assert data["action_type"] == "edit"
        assert data["edited_content"] == "<p>Fixed content</p>"
        assert data["used_vault_data"] is False
        
        # Ensure vault was NOT called
        mock_vault_context.assert_not_called()

    @pytest.mark.xfail(
        reason="Asserts the legacy retrieve_vault_context call path. After "
        "the agentic-tool refactor, vault data is fetched on-demand by the "
        "LLM via personal_data_tool inside run_Enterprise_or_Personal_tool — the "
        "endpoint never calls retrieve_vault_context anymore."
    )
    def test_report_deep_edit_stage2(self, client_fixture, mock_auth_bypass, mock_classifier, mock_llm_call, mock_vault_context):
        """
        Verify 'complex edit' intent (Stage 2) triggers vault retrieval
        and returns 'edit' action with enhanced content.
        """
        
        # 1. Mock Classifier: "edit" but potentially complex
        mock_classifier.return_value = MockClassificationResult(
            intent="edit",
            action_type="add_content",
            ai_message="Checking...",
            requires_data=True,
            requires_vault=True
        )
        
        # 2. Mock Stage 1 Assessment calls LLM: says needs vault
        # 3. Mock Stage 2 Execution calls LLM: returns HTML
        mock_llm_call.side_effect = [
            json.dumps({
                "needs_vault_data": True,
                "reason": "Needs expansion"
            }),
            "<h1>Expanded Content</h1><p>With vault data</p>" 
        ]
        
        payload = {
            "instruction": "Expand on this using my docs",
            "current_content": "<h1>Topic</h1>",
            "page_id": TEST_PAGE_ID,
            "user_id": TEST_USER_ID,
            "folder_ids": TEST_FOLDER_IDS
        }
        
        response = client_fixture.post("/composer/ai-edit", json=payload, headers={"Authorization": "Bearer dummy"})
        data = response.json()
        
        assert data["success"] is True
        assert "Expanded Content" in data["edited_content"]
        assert data["used_vault_data"] is True
        
        # Ensure vault WAS called
        mock_vault_context.assert_called()

    @pytest.mark.xfail(
        reason="Asserts the JSON envelope {needs_vault_data,edited_content,reason} "
        "from the old multi-stage Stage1/Stage2 implementation. The single-call "
        "agentic refactor returns the LLM's raw HTML directly."
    )
    def test_report_selection_mode(self, client_fixture, mock_auth_bypass, mock_classifier, mock_llm_call):
        """Verify 'selection' edit mode handles partial content."""
        
        # 1. Classifier
        mock_classifier.return_value = MockClassificationResult(
            intent="edit",
            action_type="edit_text",
            scope="selected",
            resolved_scope="element",  # Prevent auto-escalation to 'overall'
            ai_message="Rewriting selection...",
            requires_data=False,
            requires_vault=False
        )

        # 2. Stage 1 (Direct edit for selection)
        mock_llm_call.return_value = json.dumps({
            "needs_vault_data": False,
            "edited_content": "<b>Better Text</b>",
            "reason": "Rewriting selected text"
        })
        
        payload = {
            "instruction": "Make bold",
            "current_content": "Full Content",
            "selected_text": "Text",
            "page_id": TEST_PAGE_ID,
            "user_id": TEST_USER_ID,
            "edit_mode": "selection"
        }
        
        response = client_fixture.post("/composer/ai-edit", json=payload, headers={"Authorization": "Bearer dummy"})
        data = response.json()
        
        assert data["edit_mode"] == "selection"
        assert data["edited_content"] == "<b>Better Text</b>"

    def test_report_image_gen(self, client_fixture, mock_auth_bypass, mock_classifier, mock_llm_call):
        """Verify 'create_image' intent is treated as edit/add_content in 2-step flow or legacy."""
        # Note: parallel classifier maps 'create_image' to 'edit' action_type in local map
        # But classification result action_type is 'create_image'.
        # INTENT MAP in composer_context.py line 796 maps 'create_image' to 'edit'.
        
        # 1. Classifier
        mock_classifier.return_value = MockClassificationResult(
            intent="edit",
            action_type="create_image", # This will be mapped to 'edit'
            ai_message="Generating image placeholder...",
            requires_data=False,
            requires_vault=False
        )

        # 2. Stage 1 (Direct edit - inserting image placeholder)
        mock_llm_call.return_value = json.dumps({
            "needs_vault_data": False,
            "edited_content": '<img src="placeholder.png" alt="A sunset" />',
            "reason": "Added image placeholder"
        })
        
        payload = {
            "instruction": "Add an image of a sunset",
            "current_content": "Content",
            "page_id": TEST_PAGE_ID,
            "user_id": TEST_USER_ID
        }
        
        response = client_fixture.post("/composer/ai-edit", json=payload, headers={"Authorization": "Bearer dummy"})
        data = response.json()
        
        assert data["action_type"] == "edit"
        assert "placeholder" in data["edited_content"]

    @pytest.mark.xfail(
        reason="Asserts the Stage 1 assessment prompt contains 'needs_vault_data'. "
        "That two-stage assessment-then-execute pattern was removed in the "
        "agentic-tool refactor — there is no Stage 1 prompt anymore. Test "
        "needs rewriting against the unified single-call prompt."
    )
    def test_stage1_prompt_compliance(self, client_fixture, mock_auth_bypass, mock_classifier, mock_llm_call):
        """
        INTELLIGENT TEST: Verify Stage 1 System Prompt contains critical safety/logic rules.
        """
        
        # 1. Classifier
        mock_classifier.return_value = MockClassificationResult(
            intent="edit",
            action_type="edit_text",
            ai_message="Checking...",
            requires_data=False,
            requires_vault=False
        )

        # 2. Stage 1 Response
        mock_llm_call.return_value = json.dumps({"needs_vault_data": False, "edited_content": ""})
        
        payload = {
            "instruction": "Edit this", 
            "current_content": "Content", 
            "page_id": TEST_PAGE_ID, 
            "user_id": TEST_USER_ID
        }
        
        client_fixture.post("/composer/ai-edit", json=payload, headers={"Authorization": "Bearer dummy"})
        
        # Verify the calls
        # Call 1 = Stage 1 Assessment (Call 0 is probably classifier, but we mocked classifier separate function, 
        # so llm_call Call 0 is Stage 1)
        
        args, kwargs = mock_llm_call.call_args_list[0]
        
        user_prompt = kwargs.get('user_prompt', '')
        # Check for critical instructions in the prompt sent to LLM
        assert "needs_vault_data" in user_prompt
        assert "DIRECT EDIT" in user_prompt
        assert "NEEDS VAULT DATA" in user_prompt
