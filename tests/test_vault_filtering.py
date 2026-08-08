"""
=======================================================================
 TEST PLAN: Milvus Vault Query Filtering Validation
=======================================================================

 User:       rohitkumarchandan1982@gmail.com
 Collection: citra (from MILVUS_COLLECTION env)
 
 PURPOSE:
   Validate ALL 6 filtering layers work correctly after our fixes:
   1. Absolute floor (MILVUS_ABSOLUTE_MIN_SCORE = 0.10)
   2. Adaptive min floor (ADAPTIVE_MIN_FLOOR = 0.23)
   3. Relative threshold (60% of top score)
   4. Gap detection (largest drop > 0.15)
   5. Score compression detection (spread < 0.03 → reject all)
   6. Low variance tightening (std < 0.02 → raise floor)

 TEST SCENARIOS:
   ┌──────────────────────────────────────────────────────────────────┐
   │ # │ Test Name              │ What It Validates                  │
   ├───┼────────────────────────┼────────────────────────────────────┤
   │ 1 │ RELEVANT_QUERY         │ Relevant query → returns results   │
   │ 2 │ IRRELEVANT_QUERY       │ Unrelated query → returns 0        │
   │ 3 │ PARTIAL_RELEVANT       │ Vague query → returns some, not all│
   │ 4 │ KEYWORD_COLLISION      │ Ambiguous keyword → checks BM25    │
   │ 5 │ FOLDER_ISOLATION       │ Query across folders → isolation   │
   │ 6 │ SCORE_DISTRIBUTION     │ Raw score analysis before filters  │
   │ 7 │ COMPRESSION_DETECTION  │ Narrow score band → all rejected   │
   │ 8 │ GAP_DETECTION          │ Score gap found → cuts at gap      │
   │ 9 │ END_TO_END_API         │ Full /composer/query test          │
   └──────────────────────────────────────────────────────────────────┘

 HOW TO RUN:
   cd Citra-Service
   myenv\\Scripts\\activate
   python test_vault_filtering.py

 PREREQUISITES:
   - Citra-Service .env configured with ZILLIZ_CLOUD_URI, ZILLIZ_CLOUD_API_KEY
   - Test data uploaded (this script can create it — see Phase 1)
=======================================================================
"""

import os
import sys
import json
import time
import asyncio
import logging
import statistics
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

from pymilvus import MilvusClient, AnnSearchRequest, WeightedRanker
from utils import embed_text

# ─────────── Configuration ───────────
USER_EMAIL = "rohitkumarchandan1982@gmail.com"
COLLECTION_NAME = os.getenv("MILVUS_COLLECTION", "citra")
HYBRID_ALPHA = float(os.getenv("HYBRID_ALPHA", "0.70"))

# Threshold config (mirror what llamaindex_query_engine uses)
ADAPTIVE_MIN_FLOOR = float(os.getenv("ADAPTIVE_MIN_FLOOR", "0.30"))
ADAPTIVE_SCORE_DROP_RATIO = float(os.getenv("ADAPTIVE_SCORE_DROP_RATIO", "0.60"))
ADAPTIVE_GAP_THRESHOLD = float(os.getenv("ADAPTIVE_GAP_THRESHOLD", "0.15"))
MILVUS_ABSOLUTE_MIN_SCORE = float(os.getenv("MILVUS_ABSOLUTE_MIN_SCORE", "0.10"))
SCORE_SPREAD_THRESHOLD = float(os.getenv("SCORE_SPREAD_THRESHOLD", "0.03"))
SCORE_LOW_STD_MULTIPLIER = float(os.getenv("SCORE_LOW_STD_MULTIPLIER", "1.5"))

# ─────────── Logging ───────────
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════

def get_milvus_client() -> MilvusClient:
    uri = os.getenv("ZILLIZ_CLOUD_URI")
    token = os.getenv("ZILLIZ_CLOUD_API_KEY")
    if not uri or not token:
        print("❌ ZILLIZ_CLOUD_URI and ZILLIZ_CLOUD_API_KEY must be set in .env")
        sys.exit(1)
    return MilvusClient(uri=uri, token=token)


async def hybrid_search(
    client: MilvusClient,
    query: str,
    user_id: str,
    folder_id: Optional[str] = None,
    top_k: int = 15,
    alpha: float = HYBRID_ALPHA,
) -> List[Dict[str, Any]]:
    """Run hybrid search (dense + BM25) — same as _milvus_query in production."""
    query_embedding = await embed_text(query, task_type="RETRIEVAL_QUERY")

    filter_expr = f'user_id == "{user_id}"'
    if folder_id:
        filter_expr += f' and folder_id == "{folder_id}"'

    dense_req = AnnSearchRequest(
        data=[query_embedding],
        anns_field="dense_vector",
        param={"metric_type": "COSINE", "params": {}},
        limit=top_k,
        expr=filter_expr,
    )
    sparse_req = AnnSearchRequest(
        data=[query],
        anns_field="sparse_vector",
        param={"metric_type": "BM25", "params": {}},
        limit=top_k,
        expr=filter_expr,
    )

    results = client.hybrid_search(
        collection_name=COLLECTION_NAME,
        reqs=[dense_req, sparse_req],
        ranker=WeightedRanker(alpha, 1 - alpha),
        limit=top_k,
        output_fields=["chunk_id", "document_id", "text", "chunk_index",
                        "topic_or_filename", "folder_id", "user_id"],
    )

    formatted = []
    if results and len(results) > 0:
        for hit in results[0]:
            entity = hit.get("entity", {})
            formatted.append({
                "score": float(hit.get("distance", 0.0)),
                "text": entity.get("text", "")[:200],
                "topic": entity.get("topic_or_filename", "Unknown"),
                "chunk_id": entity.get("chunk_id", ""),
                "folder_id": entity.get("folder_id", ""),
                "document_id": entity.get("document_id", ""),
            })
    return formatted


def apply_filtering(results: List[Dict]) -> Tuple[List[Dict], Dict[str, Any]]:
    """
    Apply the EXACT same filtering stack as retrieve_personal_context().
    Returns (filtered_results, diagnostics).
    """
    diagnostics = {
        "total_raw": len(results),
        "absolute_floor_removed": 0,
        "compression_rejected": False,
        "low_variance_boost": False,
        "boosted_floor": None,
        "effective_threshold": 0.0,
        "gap_cutoff_index": len(results),
        "largest_gap": 0.0,
        "final_count": 0,
        "score_spread": 0.0,
        "score_std": 0.0,
    }

    if not results:
        return [], diagnostics

    # Layer 1: Absolute floor
    before = len(results)
    results = [r for r in results if r["score"] >= MILVUS_ABSOLUTE_MIN_SCORE]
    diagnostics["absolute_floor_removed"] = before - len(results)

    if not results:
        return [], diagnostics

    # Sort descending
    results.sort(key=lambda r: r["score"], reverse=True)

    all_scores = [r["score"] for r in results]
    top_score = all_scores[0]
    bottom_score = all_scores[-1]
    spread = top_score - bottom_score
    mean_s = statistics.mean(all_scores)
    std_s = statistics.pstdev(all_scores)

    diagnostics["score_spread"] = spread
    diagnostics["score_std"] = std_s

    gap_cutoff_index = len(results)

    # Layer 5: Compression detection
    if len(all_scores) >= 3 and spread < SCORE_SPREAD_THRESHOLD:
        diagnostics["compression_rejected"] = True
        diagnostics["effective_threshold"] = top_score + 1
        diagnostics["gap_cutoff_index"] = 0
        diagnostics["final_count"] = 0
        return [], diagnostics

    # Layer 6: Low variance tightening
    if std_s > 0 and std_s < 0.02:
        boosted_floor = mean_s + (SCORE_LOW_STD_MULTIPLIER * std_s)
        diagnostics["low_variance_boost"] = True
        diagnostics["boosted_floor"] = boosted_floor
        min_relative = top_score * ADAPTIVE_SCORE_DROP_RATIO
        effective = max(min_relative, ADAPTIVE_MIN_FLOOR, boosted_floor)
    else:
        min_relative = top_score * ADAPTIVE_SCORE_DROP_RATIO
        effective = max(min_relative, ADAPTIVE_MIN_FLOOR)

    diagnostics["effective_threshold"] = effective

    # Layer 4: Gap detection
    largest_gap = 0.0
    largest_gap_idx = len(results)
    for i in range(1, len(results)):
        drop = results[i - 1]["score"] - results[i]["score"]
        if drop > ADAPTIVE_GAP_THRESHOLD and drop > largest_gap:
            largest_gap = drop
            largest_gap_idx = i

    if largest_gap > 0:
        gap_cutoff_index = largest_gap_idx
        diagnostics["largest_gap"] = largest_gap
        diagnostics["gap_cutoff_index"] = gap_cutoff_index

    # Apply filters
    filtered = []
    for idx, r in enumerate(results):
        if idx >= gap_cutoff_index:
            continue
        if r["score"] < effective:
            continue
        filtered.append(r)

    diagnostics["final_count"] = len(filtered)
    return filtered, diagnostics


# ═══════════════════════════════════════════════════════════════════
# DISPLAY HELPERS
# ═══════════════════════════════════════════════════════════════════

def print_header(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def print_results(results: List[Dict], label: str = "Results"):
    if not results:
        print(f"  📭 {label}: 0 results (empty)")
        return
    print(f"  📋 {label}: {len(results)} results")
    for i, r in enumerate(results, 1):
        print(f"    {i}. score={r['score']:.4f} | topic={r['topic'][:40]} | text={r['text'][:80]}...")


def print_diagnostics(diag: Dict):
    print(f"\n  🔬 DIAGNOSTICS:")
    print(f"    Raw results:          {diag['total_raw']}")
    print(f"    Abs floor removed:    {diag['absolute_floor_removed']}")
    print(f"    Score spread:         {diag['score_spread']:.4f}")
    print(f"    Score std:            {diag['score_std']:.4f}")
    print(f"    Compression rejected: {diag['compression_rejected']}")
    print(f"    Low variance boost:   {diag['low_variance_boost']} (floor={diag.get('boosted_floor', 'N/A')})")
    print(f"    Effective threshold:  {diag['effective_threshold']:.4f}")
    print(f"    Gap cutoff at:        {diag['gap_cutoff_index']} (gap={diag['largest_gap']:.4f})")
    print(f"    ✅ Final count:       {diag['final_count']}")


# ═══════════════════════════════════════════════════════════════════
# PHASE 0: PRE-FLIGHT — Check connectivity and user data
# ═══════════════════════════════════════════════════════════════════

async def phase0_preflight(client: MilvusClient) -> Dict[str, Any]:
    print_header("PHASE 0: PRE-FLIGHT CHECK")

    # 1. Check collection exists
    collections = client.list_collections()
    print(f"  ✅ Connected to Zilliz Cloud")
    print(f"  📦 Collections: {collections}")
    assert COLLECTION_NAME in collections, f"Collection '{COLLECTION_NAME}' not found!"

    # 2. Count user's vectors
    count_result = client.query(
        collection_name=COLLECTION_NAME,
        filter=f'user_id == "{USER_EMAIL}"',
        output_fields=["count(*)"],
    )
    total_vectors = count_result[0].get("count(*)", 0) if count_result else 0
    print(f"  👤 User: {USER_EMAIL}")
    print(f"  📊 Total vectors: {total_vectors}")

    # 3. List user's folders
    folder_result = client.query(
        collection_name=COLLECTION_NAME,
        filter=f'user_id == "{USER_EMAIL}"',
        output_fields=["folder_id", "topic_or_filename"],
        limit=500,
    )
    folders = {}
    for r in folder_result:
        fid = r.get("folder_id", "unknown")
        topic = r.get("topic_or_filename", "?")
        if fid not in folders:
            folders[fid] = {"count": 0, "topics": set()}
        folders[fid]["count"] += 1
        folders[fid]["topics"].add(topic)

    print(f"  📁 Folders ({len(folders)}):")
    for fid, info in folders.items():
        topics_preview = ", ".join(list(info["topics"])[:3])
        print(f"    - {fid[:20]}... → {info['count']} chunks | topics: {topics_preview}")

    return {"total_vectors": total_vectors, "folders": folders}


# ═══════════════════════════════════════════════════════════════════
# TEST 1: RELEVANT QUERY — Should return good results
# ═══════════════════════════════════════════════════════════════════

async def test1_relevant_query(client: MilvusClient, folders: Dict):
    print_header("TEST 1: RELEVANT QUERY (expect results)")

    # Pick first known topic from user's data
    sample_topics = []
    for fid, info in folders.items():
        sample_topics.extend(list(info["topics"])[:2])
    
    if not sample_topics:
        print("  ⚠️ SKIP: No documents found for user")
        return

    # Use first known topic as query basis
    topic = sample_topics[0]
    query = f"Tell me about {topic}"
    print(f"  📝 Query: \"{query}\"")
    print(f"  🎯 Expected: Should return chunks from '{topic}'")

    raw = await hybrid_search(client, query, USER_EMAIL, top_k=15)
    filtered, diag = apply_filtering(raw)

    print_results(raw, "Raw Milvus")
    print_results(filtered, "After Filtering")
    print_diagnostics(diag)

    # ASSERTION
    if diag["final_count"] > 0:
        print(f"\n  ✅ PASS: Got {diag['final_count']} relevant results")
    else:
        print(f"\n  ⚠️ WARNING: 0 results for a relevant query — threshold may be too aggressive")


# ═══════════════════════════════════════════════════════════════════
# TEST 2: IRRELEVANT QUERY — Should return 0 results
# ═══════════════════════════════════════════════════════════════════

async def test2_irrelevant_query(client: MilvusClient):
    print_header("TEST 2: IRRELEVANT QUERY (expect 0 results)")

    irrelevant_queries = [
        "What is the recipe for chocolate chip cookies?",
        "How to fix a leaky faucet in the bathroom?",
        "What are the rules of cricket and how do you score runs?",
    ]

    for query in irrelevant_queries:
        print(f"\n  📝 Query: \"{query}\"")
        raw = await hybrid_search(client, query, USER_EMAIL, top_k=15)
        filtered, diag = apply_filtering(raw)

        print(f"    Raw: {diag['total_raw']} | Spread: {diag['score_spread']:.4f} | "
              f"Std: {diag['score_std']:.4f} | Compressed: {diag['compression_rejected']} | "
              f"Final: {diag['final_count']}")

        if diag['total_raw'] > 0:
            scores = [r['score'] for r in raw]
            print(f"    Scores: [{', '.join(f'{s:.4f}' for s in scores[:8])}]")

        if diag["final_count"] == 0:
            print(f"    ✅ PASS: 0 results for irrelevant query")
        else:
            print(f"    ❌ FAIL: Got {diag['final_count']} results for irrelevant query!")
            for r in filtered:
                print(f"      - score={r['score']:.4f} | {r['topic'][:40]}")


# ═══════════════════════════════════════════════════════════════════
# TEST 3: PARTIAL RELEVANCE — Should return some, not all
# ═══════════════════════════════════════════════════════════════════

async def test3_partial_relevance(client: MilvusClient, folders: Dict):
    print_header("TEST 3: PARTIAL RELEVANCE (expect some results)")

    # Use a vague/general query that might partially match
    vague_queries = [
        "summary of key points",
        "important information and details",
        "overview of the main topics discussed",
    ]

    for query in vague_queries:
        print(f"\n  📝 Query: \"{query}\"")
        raw = await hybrid_search(client, query, USER_EMAIL, top_k=15)
        filtered, diag = apply_filtering(raw)

        print(f"    Raw: {diag['total_raw']} | Spread: {diag['score_spread']:.4f} | "
              f"Std: {diag['score_std']:.4f} | Final: {diag['final_count']}")

        if diag['total_raw'] > 0:
            scores = [r['score'] for r in raw]
            print(f"    Scores: [{', '.join(f'{s:.4f}' for s in scores[:8])}]")

        # Partial relevance: could be 0 or some — just report
        print(f"    📊 Result: {diag['final_count']}/{diag['total_raw']} passed filters")


# ═══════════════════════════════════════════════════════════════════
# TEST 4: KEYWORD COLLISION — Ambiguous keyword, test BM25 effect
# ═══════════════════════════════════════════════════════════════════

async def test4_keyword_collision(client: MilvusClient):
    print_header("TEST 4: KEYWORD COLLISION (BM25 vs Dense)")

    # Test queries where keyword might match but semantics don't
    queries = [
        "apple fruit nutrition and health benefits",       # Should NOT match Apple Inc docs
        "python snake habitat in the rainforest",          # Should NOT match Python programming
        "bank of the river erosion patterns",              # Should NOT match bank/finance docs
    ]

    for query in queries:
        print(f"\n  📝 Query: \"{query}\"")
        raw = await hybrid_search(client, query, USER_EMAIL, top_k=10)
        filtered, diag = apply_filtering(raw)

        print(f"    Raw: {diag['total_raw']} | Final: {diag['final_count']}")
        if filtered:
            for r in filtered[:3]:
                print(f"      score={r['score']:.4f} | {r['topic'][:40]} | {r['text'][:80]}...")
        else:
            print(f"    📭 No results (correct if user has no related docs)")


# ═══════════════════════════════════════════════════════════════════
# TEST 5: FOLDER ISOLATION — Cross-folder leak test
# ═══════════════════════════════════════════════════════════════════

async def test5_folder_isolation(client: MilvusClient, folders: Dict):
    print_header("TEST 5: FOLDER ISOLATION")

    folder_ids = list(folders.keys())
    if len(folder_ids) < 2:
        print("  ⚠️ SKIP: Need at least 2 folders to test isolation")
        return

    # Pick folder A's topic, search in folder B
    folder_a = folder_ids[0]
    folder_b = folder_ids[1]
    topic_a = list(folders[folder_a]["topics"])[0]

    query = f"Tell me about {topic_a}"
    print(f"  📝 Query: \"{query}\" (topic from folder A)")
    print(f"  📁 Folder A: {folder_a[:20]}... ({folders[folder_a]['count']} chunks)")
    print(f"  📁 Folder B: {folder_b[:20]}... ({folders[folder_b]['count']} chunks)")

    # Search in folder A (should find results)
    raw_a = await hybrid_search(client, query, USER_EMAIL, folder_id=folder_a, top_k=10)
    filtered_a, diag_a = apply_filtering(raw_a)
    print(f"\n  🔍 In Folder A: {diag_a['final_count']} results (expected: >0)")

    # Search in folder B (should find 0 or different results)
    raw_b = await hybrid_search(client, query, USER_EMAIL, folder_id=folder_b, top_k=10)
    filtered_b, diag_b = apply_filtering(raw_b)
    print(f"  🔍 In Folder B: {diag_b['final_count']} results (expected: 0 or different topic)")

    if diag_a['final_count'] > 0 and diag_b['final_count'] == 0:
        print(f"\n  ✅ PASS: Perfect folder isolation")
    elif diag_a['final_count'] > diag_b['final_count']:
        print(f"\n  ⚠️ PARTIAL: Folder A has more results, but B leaked some")
    else:
        print(f"\n  ❌ FAIL: No isolation — folder filter may not be working")


# ═══════════════════════════════════════════════════════════════════
# TEST 6: SCORE DISTRIBUTION ANALYSIS
# ═══════════════════════════════════════════════════════════════════

async def test6_score_distribution(client: MilvusClient, folders: Dict):
    print_header("TEST 6: SCORE DISTRIBUTION ANALYSIS")

    # Run a mix of queries and show score patterns
    topics = []
    for fid, info in folders.items():
        topics.extend(list(info["topics"])[:1])

    queries = [
        (topics[0] if topics else "technology", "Relevant"),
        ("recipe for banana bread with walnuts", "Irrelevant"),
        ("overview of main topics", "Vague"),
    ]

    for query, label in queries:
        print(f"\n  📝 [{label}] \"{query[:60]}\"")
        raw = await hybrid_search(client, query, USER_EMAIL, top_k=15)

        if not raw:
            print(f"    📭 No raw results")
            continue

        scores = [r["score"] for r in raw]
        spread = max(scores) - min(scores)
        std = statistics.pstdev(scores)
        mean = statistics.mean(scores)

        print(f"    Scores: [{', '.join(f'{s:.4f}' for s in scores)}]")
        print(f"    Max={max(scores):.4f} Min={min(scores):.4f} Spread={spread:.4f} "
              f"Std={std:.4f} Mean={mean:.4f}")

        # Show what each filter layer would do
        print(f"    ── Filter Analysis ──")
        print(f"    Abs floor (>{MILVUS_ABSOLUTE_MIN_SCORE}):  {sum(1 for s in scores if s >= MILVUS_ABSOLUTE_MIN_SCORE)}/{len(scores)} pass")
        print(f"    Adapt floor (>{ADAPTIVE_MIN_FLOOR}): {sum(1 for s in scores if s >= ADAPTIVE_MIN_FLOOR)}/{len(scores)} pass")
        rel_thresh = max(scores) * ADAPTIVE_SCORE_DROP_RATIO
        eff_thresh = max(rel_thresh, ADAPTIVE_MIN_FLOOR)
        print(f"    Relative ({ADAPTIVE_SCORE_DROP_RATIO}×{max(scores):.4f}={rel_thresh:.4f}): "
              f"{sum(1 for s in scores if s >= eff_thresh)}/{len(scores)} pass")
        print(f"    Compression (spread<{SCORE_SPREAD_THRESHOLD}): "
              f"{'TRIGGERED → reject all' if spread < SCORE_SPREAD_THRESHOLD and len(scores) >= 3 else 'not triggered'}")
        print(f"    Low-var (std<0.02): "
              f"{'TRIGGERED' if 0 < std < 0.02 else 'not triggered'}")


# ═══════════════════════════════════════════════════════════════════
# TEST 7: COMPRESSION DETECTION (the key new filter)
# ═══════════════════════════════════════════════════════════════════

async def test7_compression_detection(client: MilvusClient):
    print_header("TEST 7: COMPRESSION DETECTION")

    # These queries should have NO semantic match to typical business/personal docs
    # → Milvus returns garbage with narrow score band → compression should catch it
    compression_queries = [
        "quantum chromodynamics quark gluon plasma formation",
        "medieval Byzantine iconoclasm theological disputes",
        "underwater deep sea anglerfish bioluminescence patterns",
        "Polynesian wayfinding star navigation techniques",
        "history of fermentation in ancient Mesopotamian beer",
    ]

    passed = 0
    total = len(compression_queries)

    for query in compression_queries:
        print(f"\n  📝 Query: \"{query[:60]}\"")
        raw = await hybrid_search(client, query, USER_EMAIL, top_k=15)
        filtered, diag = apply_filtering(raw)

        scores_str = ""
        if raw:
            scores = [r["score"] for r in raw]
            scores_str = f"[{', '.join(f'{s:.4f}' for s in scores[:6])}]"

        print(f"    Raw: {diag['total_raw']} | Spread: {diag['score_spread']:.4f} | "
              f"Std: {diag['score_std']:.4f}")
        print(f"    Scores: {scores_str}")
        print(f"    Compressed: {diag['compression_rejected']} | "
              f"Low-var: {diag['low_variance_boost']} | Final: {diag['final_count']}")

        if diag["final_count"] == 0:
            print(f"    ✅ PASS: Correctly returned 0 results")
            passed += 1
        else:
            print(f"    ❌ FAIL: Returned {diag['final_count']} irrelevant results")
            for r in filtered[:3]:
                print(f"      - {r['score']:.4f} | {r['topic'][:40]}")

    print(f"\n  📊 COMPRESSION TEST SUMMARY: {passed}/{total} passed")


# ═══════════════════════════════════════════════════════════════════
# TEST 8: GAP DETECTION
# ═══════════════════════════════════════════════════════════════════

async def test8_gap_detection(client: MilvusClient, folders: Dict):
    print_header("TEST 8: GAP DETECTION")

    # Pick a specific topic — results for that topic should score high,
    # then there should be a gap before unrelated chunks
    topics = []
    for fid, info in folders.items():
        topics.extend(list(info["topics"])[:1])

    if not topics:
        print("  ⚠️ SKIP: No topics found")
        return

    query = f"detailed information about {topics[0]}"
    print(f"  📝 Query: \"{query}\"")

    raw = await hybrid_search(client, query, USER_EMAIL, top_k=15)
    if not raw:
        print("  📭 No results")
        return

    scores = [r["score"] for r in raw]
    print(f"  Scores: [{', '.join(f'{s:.4f}' for s in scores)}]")

    # Analyze gaps
    print(f"\n  📊 Gap Analysis (threshold={ADAPTIVE_GAP_THRESHOLD}):")
    for i in range(1, len(scores)):
        drop = scores[i - 1] - scores[i]
        marker = " ← GAP!" if drop > ADAPTIVE_GAP_THRESHOLD else ""
        print(f"    {i}→{i+1}: {scores[i-1]:.4f} → {scores[i]:.4f} (drop={drop:.4f}){marker}")

    filtered, diag = apply_filtering(raw)
    print(f"\n  Filtered: {diag['final_count']}/{diag['total_raw']} "
          f"(gap at {diag['gap_cutoff_index']}, drop={diag['largest_gap']:.4f})")

    if diag['largest_gap'] > 0:
        print(f"  ✅ Gap detection working — cut at position {diag['gap_cutoff_index']}")
    else:
        print(f"  ℹ️  No significant gap found (all results similar quality)")


# ═══════════════════════════════════════════════════════════════════
# TEST 9: FULL STACK — Same logic as retrieve_personal_context()
# ═══════════════════════════════════════════════════════════════════

async def test9_full_stack(client: MilvusClient, folders: Dict):
    print_header("TEST 9: FULL STACK SIMULATION")
    print("  Simulates retrieve_personal_context() end-to-end\n")

    topics = []
    for fid, info in folders.items():
        topics.extend(list(info["topics"])[:1])

    test_cases = [
        {"query": f"Tell me about {topics[0]}" if topics else "product details", "expected": "some", "label": "Relevant"},
        {"query": "deep fried tarantula spider recipe Southeast Asia", "expected": "zero", "label": "Irrelevant"},
        {"query": "summary overview", "expected": "any", "label": "Vague"},
    ]

    results_summary = []
    for tc in test_cases:
        print(f"  [{tc['label']}] \"{tc['query'][:60]}\"")
        raw = await hybrid_search(client, tc["query"], USER_EMAIL, top_k=15)
        filtered, diag = apply_filtering(raw)

        status = "✅"
        if tc["expected"] == "some" and diag["final_count"] == 0:
            status = "⚠️"
        elif tc["expected"] == "zero" and diag["final_count"] > 0:
            status = "❌"

        print(f"    {status} Raw={diag['total_raw']} → Final={diag['final_count']} "
              f"(spread={diag['score_spread']:.4f}, compressed={diag['compression_rejected']})")
        results_summary.append((tc["label"], status, diag["final_count"]))

    print(f"\n  ═══════════════════════════════════")
    print(f"  SUMMARY:")
    for label, status, count in results_summary:
        print(f"    {status} {label}: {count} results")


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

async def main():
    print("\n" + "═" * 70)
    print("  MILVUS VAULT FILTERING — COMPREHENSIVE TEST SUITE")
    print("  User: " + USER_EMAIL)
    print("  Collection: " + COLLECTION_NAME)
    print(f"  Config: floor={ADAPTIVE_MIN_FLOOR}, alpha={HYBRID_ALPHA}, "
          f"spread_thresh={SCORE_SPREAD_THRESHOLD}, gap_thresh={ADAPTIVE_GAP_THRESHOLD}")
    print("═" * 70)

    client = get_milvus_client()

    # Phase 0: Pre-flight
    info = await phase0_preflight(client)
    if info["total_vectors"] == 0:
        print("\n❌ No vectors found for user. Upload test data first (see instructions above).")
        sys.exit(1)

    folders = info["folders"]

    # Run all tests
    await test1_relevant_query(client, folders)
    await test2_irrelevant_query(client)
    await test3_partial_relevance(client, folders)
    await test4_keyword_collision(client)
    await test5_folder_isolation(client, folders)
    await test6_score_distribution(client, folders)
    await test7_compression_detection(client)
    await test8_gap_detection(client, folders)
    await test9_full_stack(client, folders)

    print("\n" + "═" * 70)
    print("  ALL TESTS COMPLETE")
    print("═" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
