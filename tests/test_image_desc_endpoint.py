# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

import asyncio
import aiohttp
import json

async def test_image_description():
    url = "http://localhost:8000/composer/generate-image-description"
    
    payload = {
        "user_query": "Show a growth chart of our AI adoption",
        "page_title": "AI Strategy 2025",
        "page_snippet": "We have seen a 300% increase in AI adoption across all departments. The engineering team leads the way...",
        "user_id": "test_user_123",
        "folder_ids": ["folder_abc"] # Mock folder
    }
    
    print(f"Testing {url}...")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                print(f"Status: {response.status}")
                result = await response.json()
                print(f"Response: {json.dumps(result, indent=2)}")
                
                if response.status == 200 and result.get("success"):
                    print("\n✅ API Test Passed!")
                    print(f"Generated Description: {result.get('image_description')}")
                else:
                    print("\n❌ API Test Failed")
                    
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_image_description())
