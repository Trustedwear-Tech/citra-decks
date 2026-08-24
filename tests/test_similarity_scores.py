# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
Test direct similarity between query and TrustedWear document chunks
"""
import os
import asyncio
from dotenv import load_dotenv
from pymilvus import MilvusClient
from utils import embed_text

load_dotenv()

async def test_similarity():
    # Initialize Milvus client
    client = MilvusClient(
        uri=os.getenv('ZILLIZ_CLOUD_URI'),
        token=os.getenv('ZILLIZ_CLOUD_API_KEY')
    )
    
    collection_name = "dev"
    user_id = "rohit@citra-ai.com"
    document_id = "d15738cd-935c-46a8-af2f-2fde0fdcf7a6"
    
    print(f"\n🔍 Testing similarity for TrustedWear document")
    print(f"   User ID: {user_id}")
    print(f"   Document ID: {document_id}\n")
    
    # Get the query embedding
    query = "explain about trustedwear products"
    print(f"📝 Query: {query}")
    query_embedding = await embed_text(query)
    print(f"✅ Query embedding generated: {len(query_embedding)} dimensions\n")
    
    # Search with dense vector only (to test if dense search works)
    print("🔍 Testing DENSE-ONLY search...")
    dense_results = client.search(
        collection_name=collection_name,
        data=[query_embedding],
        anns_field="dense_vector",
        filter=f'user_id == "{user_id}"',
        limit=5,
        output_fields=["chunk_id", "document_id", "text", "chunk_index"],
        search_params={"metric_type": "COSINE", "params": {}}
    )
    
    print(f"✅ Dense search returned {len(dense_results[0])} results\n")
    for idx, hit in enumerate(dense_results[0], 1):
        score = hit.get('distance', 0.0)
        text_preview = hit.get('text', '')[:100]
        chunk_idx = hit.get('chunk_index', '?')
        print(f"{idx}. Score: {score:.4f} | Chunk {chunk_idx}")
        print(f"   Text: {text_preview}...")
        print()
    
    # Now test hybrid search with WeightedRanker
    print("\n🔍 Testing HYBRID search with WeightedRanker (dense + BM25)...")
    from pymilvus import AnnSearchRequest, WeightedRanker
    
    dense_req = AnnSearchRequest(
        data=[query_embedding],
        anns_field="dense_vector",
        param={"metric_type": "COSINE", "params": {}},
        limit=15,
        expr=f'user_id == "{user_id}"'
    )
    
    sparse_req = AnnSearchRequest(
        data=[query],  # Query text for server-side BM25
        anns_field="sparse_vector",
        param={"metric_type": "BM25", "params": {}},
        limit=15,
        expr=f'user_id == "{user_id}"'
    )
    
    hybrid_results = client.hybrid_search(
        collection_name=collection_name,
        reqs=[dense_req, sparse_req],
        ranker=WeightedRanker(0.8, 0.2),  # 80% dense, 20% sparse - preserves similarity scores
        limit=15,
        output_fields=["chunk_id", "document_id", "text", "chunk_index"]
    )
    
    print(f"✅ Hybrid search returned {len(hybrid_results[0])} results\n")
    for idx, hit in enumerate(hybrid_results[0], 1):
        score = hit.get('distance', 0.0)
        text_preview = hit.get('text', '')[:100]
        chunk_idx = hit.get('chunk_index', '?')
        print(f"{idx}. Score: {score:.4f} | Chunk {chunk_idx}")
        print(f"   Text: {text_preview}...")
        print()

if __name__ == "__main__":
    asyncio.run(test_similarity())
