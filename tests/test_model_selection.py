# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

import asyncio
import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add the current directory to sys.path to import orchestrator
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock the expensive imports and dependencies
with patch('agentic_rag.orchestrator.get_source_provider'), \
     patch('agentic_rag.orchestrator.SimplifiedStrategyPlanner'), \
     patch('agentic_rag.orchestrator.ContextMerger'), \
     patch('agentic_rag.orchestrator.QueryOrchestrator._build_graph'):
    from agentic_rag.orchestrator import QueryOrchestrator

class TestModelSelection(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.orchestrator = QueryOrchestrator()
        # Mock reply function - it's imported inside the method from query module
        self.reply_patcher = patch('query.reply', return_value="Mocked Response")
        self.mock_reply = self.reply_patcher.start()

        
    def tearDown(self):
        self.reply_patcher.stop()

    async def test_llm_selected_for_text_only(self):
        """Test that LLM is used when no image attachments are present in model_only_mode."""
        query = "Hello, how are you?"
        user_id = "test_user"
        
        # Call process_query in model_only_mode
        await self.orchestrator.process_query(
            query=query,
            user_id=user_id,
            use_personal_data=False, # This triggers model_only_mode if enterprise is also disabled
            use_enterprise_data=False
        )

        
        # Check if reply was called with LLM
        # args[0] is prompt, args[1] is model
        # Model is dynamically determined by get_default_model()
        self.assertTrue(self.mock_reply.call_args[0][1] is not None, "Model should not be None")

    async def test_llm_vision_selected_for_images(self):
        """Test that LLM is used when image attachments are present in model_only_mode."""
        query = "What is in this image?"
        user_id = "test_user"
        attachments = [
            {"name": "test.png", "mimeType": "image/png", "base64": "fake_data"}
        ]
        
        # Call process_query in model_only_mode with attachments
        await self.orchestrator.process_query(
            query=query,
            user_id=user_id,
            use_personal_data=False,
            use_enterprise_data=False,
            multimodal_attachments=attachments
        )
        
        # Check if reply was called with LLM
        self.assertEqual(self.mock_reply.call_args[0][1], "llm-3-flash-preview")

if __name__ == '__main__':
    unittest.main()
