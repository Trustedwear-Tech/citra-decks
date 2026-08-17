#!/usr/bin/env python3
# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

"""Test xAI SDK internet search directly"""

import os
from xai_sdk import Client
from xai_sdk.search import SearchParameters, web_source
from xai_sdk.chat import user

# Get API key
api_key = os.getenv('XAI_API_KEY')
if not api_key:
    print("❌ XAI_API_KEY not set")
    exit(1)

print("🔧 Testing xAI SDK internet search...")
print(f"API Key present: {bool(api_key)}")

# Create client
client = Client(api_key=api_key)

# Test 1: Simple search with mode="on"
print("\n" + "="*60)
print("TEST 1: Simple search with mode='on'")
print("="*60)

chat = client.chat.create(
    model=os.environ.get('SEARCH_MODEL', 'grok-3'),
    search_parameters=SearchParameters(
        mode='on',
        return_citations=True,
        sources=[web_source(country='IN')]
    )
)

chat.append(user('What is the latest news in India today?'))
response = chat.sample()

print(f"\n✅ Response: {response.content[:200]}...")
print(f"📊 Sources used: {response.usage.num_sources_used if hasattr(response, 'usage') else 'N/A'}")
if hasattr(response, 'citations') and response.citations:
    print(f"🔗 Citations: {len(response.citations)} URLs")
    for i, citation in enumerate(response.citations[:3]):
        print(f"   {i+1}. {citation}")

# Test 2: Search with mode="auto"
print("\n" + "="*60)
print("TEST 2: Search with mode='auto'")
print("="*60)

chat2 = client.chat.create(
    model=os.environ.get('SEARCH_MODEL', 'grok-3'),
    search_parameters=SearchParameters(
        mode='auto',
        return_citations=True,
        sources=[web_source(country='IN')]
    )
)

chat2.append(user('What is 2+2?'))
response2 = chat2.sample()

print(f"\n✅ Response: {response2.content}")
print(f"📊 Sources used: {response2.usage.num_sources_used if hasattr(response2, 'usage') else 'N/A'}")

print("\n" + "="*60)
print("✅ Tests completed!")
print("="*60)
