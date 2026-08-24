# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
=======================================================================
 COMPREHENSIVE MILVUS FILTERING TEST WITH GENERATED DATA
=======================================================================

 Creates two test folders with distinct topics:
   - Folder "Solar Energy" → 10 chunks about solar panels, renewable energy
   - Folder "Marine Biology" → 10 chunks about ocean life, coral reefs

 Then runs 12 targeted test scenarios to validate ALL filtering layers.
 Cleans up all test data at the end.

 HOW TO RUN:
   cd Citra-Service
   myenv\\Scripts\\activate
   python test_vault_filtering_full.py
=======================================================================
"""

import os
import sys
import uuid
import time
import asyncio
import hashlib
import statistics
import logging
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

from pymilvus import MilvusClient
from utils import embed_text

# ─────────── Config ───────────
USER_EMAIL = "rohitkumarchandan1982@gmail.com"
COLLECTION_NAME = os.getenv("MILVUS_COLLECTION", "citra")

# Threshold config (mirrors llamaindex_query_engine.py — pure dense COSINE, no BM25)
ADAPTIVE_MIN_FLOOR = float(os.getenv("ADAPTIVE_MIN_FLOOR", "0.30"))
ADAPTIVE_SCORE_DROP_RATIO = float(os.getenv("ADAPTIVE_SCORE_DROP_RATIO", "0.60"))
ADAPTIVE_GAP_THRESHOLD = float(os.getenv("ADAPTIVE_GAP_THRESHOLD", "0.15"))
MILVUS_ABSOLUTE_MIN_SCORE = float(os.getenv("MILVUS_ABSOLUTE_MIN_SCORE", "0.10"))
TOP_SCORE_MINIMUM = float(os.getenv("TOP_SCORE_MINIMUM", "0.50"))
TOP_SCORE_STANDOUT = float(os.getenv("TOP_SCORE_STANDOUT", "0.15"))
SCORE_SPREAD_THRESHOLD = float(os.getenv("SCORE_SPREAD_THRESHOLD", "0.03"))
SCORE_LOW_STD_MULTIPLIER = float(os.getenv("SCORE_LOW_STD_MULTIPLIER", "1.5"))
SINGLE_RESULT_MIN_FLOOR = float(os.getenv("SINGLE_RESULT_MIN_FLOOR", "0.40"))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# TEST DATA — Two distinct domains for relevance/isolation testing
# ═══════════════════════════════════════════════════════════════════

TEST_FOLDER_SOLAR = f"test-solar-{uuid.uuid4().hex[:8]}"
TEST_FOLDER_MARINE = f"test-marine-{uuid.uuid4().hex[:8]}"
TEST_DOC_SOLAR = f"test-doc-solar-{uuid.uuid4().hex[:8]}"
TEST_DOC_MARINE = f"test-doc-marine-{uuid.uuid4().hex[:8]}"

SOLAR_CHUNKS = [
    "Solar photovoltaic panels convert sunlight directly into electricity using semiconductor materials like silicon. When photons from sunlight hit the solar cell, they knock electrons free from atoms, generating a flow of electricity. This photovoltaic effect was first discovered by Edmond Becquerel in 1839.",
    "The efficiency of modern monocrystalline solar panels typically ranges from 20% to 24%, while polycrystalline panels achieve 15% to 20% efficiency. Newer technologies like perovskite solar cells have reached laboratory efficiencies exceeding 25%, showing promise for next-generation solar energy.",
    "Solar panel installation costs have dropped by 89% since 2010, making rooftop solar increasingly affordable for homeowners. The average residential solar system costs between $15,000 and $25,000 before tax credits, with the federal solar investment tax credit covering 30% of installation costs.",
    "Net metering allows solar panel owners to sell excess electricity back to the grid, effectively spinning their meter backwards. This policy has been a key driver of residential solar adoption, though some utilities have proposed reducing net metering rates for new solar customers.",
    "Battery storage systems like the Tesla Powerwall pair with solar panels to store excess energy generated during the day for use at night. A typical home battery stores 10-15 kWh, enough to power essential appliances through the evening. Lithium-ion batteries currently dominate the residential storage market.",
    "Solar farms and utility-scale solar installations generate electricity at costs competitive with natural gas and coal power plants. The levelized cost of solar energy (LCOE) has fallen below $30 per megawatt-hour in many regions, making it the cheapest source of new electricity generation globally.",
    "Solar panel degradation occurs at approximately 0.5% per year, meaning panels still produce about 87% of their original output after 25 years. Most manufacturers offer 25-year performance warranties guaranteeing at least 80% of rated power output.",
    "Bifacial solar panels can capture light on both sides, increasing energy production by 10-30% compared to standard monofacial panels. These panels work especially well over reflective surfaces like white rooftops or snow-covered ground.",
    "Community solar programs allow renters and homeowners with unsuitable roofs to benefit from solar energy by subscribing to a shared solar array. Subscribers receive credits on their electricity bills proportional to their share of the solar farm's output.",
    "The environmental impact of solar panels includes the energy-intensive manufacturing process, which produces 20-50 grams of CO2 per kilowatt-hour over the panel's lifetime. However, this is still dramatically lower than coal (820g) or natural gas (490g) power generation.",
]

MARINE_CHUNKS = [
    "Coral reefs are underwater ecosystems built by colonies of tiny animals called coral polyps. These structures support approximately 25% of all marine species despite covering less than 1% of the ocean floor. The Great Barrier Reef, stretching 2,300 kilometers along Australia's coast, is the largest coral reef system on Earth.",
    "Ocean acidification, caused by the absorption of excess atmospheric CO2, threatens marine organisms that build calcium carbonate shells and skeletons. Since the industrial revolution, ocean pH has decreased by 0.1 units, representing a 30% increase in acidity. This poses severe risks to shellfish, corals, and plankton populations.",
    "Deep sea hydrothermal vents support unique ecosystems that thrive in extreme conditions without sunlight. Giant tube worms, which can grow up to 2 meters long, rely on chemosynthetic bacteria that convert hydrogen sulfide from the vents into energy, forming the base of the food chain.",
    "Humpback whales undertake one of the longest migrations of any mammal, traveling up to 8,000 kilometers between their tropical breeding grounds and polar feeding areas. During feeding season, a single humpback whale can consume up to 1,360 kilograms of krill and small fish per day.",
    "Sea turtles navigate vast ocean distances using the Earth's magnetic field for orientation. Five of the seven sea turtle species are classified as endangered, with threats including plastic pollution, entanglement in fishing nets, habitat loss, and the harvesting of eggs from nesting beaches.",
    "Bioluminescence in the deep ocean is produced by over 75% of deep-sea organisms. Animals like the anglerfish, comb jellies, and lanternfish use chemical reactions to produce light for attracting prey, finding mates, or evading predators in the perpetual darkness below 200 meters.",
    "Mangrove forests serve as critical nursery habitats for commercial fish species, protecting juvenile fish from predators while providing abundant food resources. A single hectare of mangrove can support the production of nearly one metric ton of fish and shrimp annually.",
    "The Mariana Trench reaches a depth of approximately 11,034 meters, making it the deepest known point in the ocean. Despite immense pressure exceeding 1,000 atmospheres, unique organisms including amphipods and xenophyophores have been found thriving at these extreme depths.",
    "Phytoplankton are microscopic marine plants responsible for producing approximately 50% of the Earth's oxygen through photosynthesis. These tiny organisms form the foundation of the marine food web and play a crucial role in the global carbon cycle by absorbing atmospheric CO2.",
    "Marine protected areas (MPAs) have been shown to increase fish biomass by an average of 670% compared to unprotected areas. Currently, about 8% of the world's oceans are designated as MPAs, though scientists recommend protecting at least 30% to maintain healthy ocean ecosystems.",
]

# Track all inserted chunk_ids for cleanup
ALL_TEST_CHUNK_IDS = []


# ═══════════════════════════════════════════════════════════════════
# DATA MANAGEMENT
# ═══════════════════════════════════════════════════════════════════

def get_client() -> MilvusClient:
    uri = os.getenv("ZILLIZ_CLOUD_URI")
    token = os.getenv("ZILLIZ_CLOUD_API_KEY")
    if not uri or not token:
        print("❌ Missing ZILLIZ_CLOUD_URI or ZILLIZ_CLOUD_API_KEY in .env")
        sys.exit(1)
    return MilvusClient(uri=uri, token=token)


async def insert_test_data(client: MilvusClient):
    """Generate embeddings and insert test chunks into Milvus."""
    print_header("PHASE 1: INSERTING TEST DATA")

    for folder_id, doc_id, topic, chunks in [
        (TEST_FOLDER_SOLAR, TEST_DOC_SOLAR, "Solar Energy Research", SOLAR_CHUNKS),
        (TEST_FOLDER_MARINE, TEST_DOC_MARINE, "Marine Biology Research", MARINE_CHUNKS),
    ]:
        print(f"\n  📁 Folder: {folder_id}")
        print(f"  📄 Doc: {doc_id} ({topic})")
        print(f"  📝 Embedding {len(chunks)} chunks...")

        # Generate embeddings for all chunks
        embeddings = []
        for i, chunk in enumerate(chunks):
            emb = await embed_text(chunk, task_type="RETRIEVAL_DOCUMENT")
            embeddings.append(emb)
            print(f"    ✅ Chunk {i+1}/{len(chunks)} embedded ({len(emb)}D)")

        # Build Milvus data
        milvus_data = []
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            chunk_id = f"test-{uuid.uuid4().hex}"
            ALL_TEST_CHUNK_IDS.append(chunk_id)

            id_hash = int(hashlib.sha256(chunk_id.encode()).hexdigest()[:15], 16)
            milvus_data.append({
                "primary_key": id_hash,
                "chunk_id": chunk_id,
                "dense_vector": emb,
                "user_id": USER_EMAIL,
                "document_id": doc_id,
                "folder_id": folder_id,
                "entity_id": "none",
                "text": chunk,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "created_at": int(time.time() * 1000),
                "topic_or_filename": topic,
                "source_type": "document",
            })

        # Insert batch
        res = client.insert(collection_name=COLLECTION_NAME, data=milvus_data)
        count = res.get("insert_count", len(milvus_data))
        print(f"  ✅ Inserted {count} vectors into Milvus")

    print(f"\n  📊 Total test vectors: {len(ALL_TEST_CHUNK_IDS)}")
    print(f"  ⏳ Waiting 3s for index to update...")
    await asyncio.sleep(3)


async def cleanup_test_data(client: MilvusClient):
    """Delete all test vectors by chunk_id."""
    print_header("CLEANUP: REMOVING TEST DATA")

    if not ALL_TEST_CHUNK_IDS:
        print("  ℹ️  No test data to clean up")
        return

    # Delete by filter on chunk_id
    for folder_id in [TEST_FOLDER_SOLAR, TEST_FOLDER_MARINE]:
        try:
            res = client.delete(
                collection_name=COLLECTION_NAME,
                filter=f'folder_id == "{folder_id}"',
            )
            print(f"  🗑️ Deleted vectors for folder {folder_id[:30]}...")
        except Exception as e:
            print(f"  ⚠️ Cleanup error for {folder_id[:30]}: {e}")

    print(f"  ✅ Cleanup complete")


# ═══════════════════════════════════════════════════════════════════
# SEARCH + FILTER (same as test_vault_filtering.py)
# ═══════════════════════════════════════════════════════════════════

async def dense_search(
    client: MilvusClient, query: str, user_id: str,
    folder_id: Optional[str] = None, top_k: int = 20,
) -> List[Dict]:
    """Pure dense COSINE search — no BM25, no hybrid, no arctan normalization."""
    emb = await embed_text(query, task_type="RETRIEVAL_QUERY")
    filt = f'user_id == "{user_id}"'
    if folder_id:
        filt += f' and folder_id == "{folder_id}"'

    results = client.search(
        collection_name=COLLECTION_NAME,
        data=[emb],
        anns_field="dense_vector",
        search_params={"metric_type": "COSINE", "params": {}},
        limit=top_k,
        filter=filt,
        output_fields=["chunk_id", "document_id", "text", "chunk_index",
                        "topic_or_filename", "folder_id"],
    )
    out = []
    if results and results[0]:
        for hit in results[0]:
            e = hit.get("entity", {})
            out.append({
                "score": float(hit.get("distance", 0.0)),
                "text": e.get("text", "")[:150],
                "topic": e.get("topic_or_filename", "?"),
                "folder_id": e.get("folder_id", ""),
                "document_id": e.get("document_id", ""),
                "chunk_id": e.get("chunk_id", ""),
            })
    return out


def apply_filtering(results: List[Dict]) -> Tuple[List[Dict], Dict]:
    diag = {
        "total_raw": len(results), "absolute_floor_removed": 0,
        "single_result_rejected": False, "multi_signal_rejected": False, "compression_rejected": False,
        "low_variance_boost": False, "boosted_floor": None,
        "effective_threshold": 0.0, "gap_cutoff_index": len(results),
        "largest_gap": 0.0, "final_count": 0,
        "score_spread": 0.0, "score_std": 0.0, "score_mean": 0.0,
        "top_standout": 0.0,
    }
    if not results:
        return [], diag

    before = len(results)
    results = [r for r in results if r["score"] >= MILVUS_ABSOLUTE_MIN_SCORE]
    diag["absolute_floor_removed"] = before - len(results)
    if not results:
        return [], diag

    results.sort(key=lambda r: r["score"], reverse=True)
    scores = [r["score"] for r in results]
    top, bot = scores[0], scores[-1]
    spread = top - bot
    mean_s = statistics.mean(scores)
    std_s = statistics.pstdev(scores)
    top_standout = top - mean_s
    diag.update(score_spread=spread, score_std=std_s, score_mean=mean_s, top_standout=top_standout)

    gap_cutoff = len(results)

    # Single-result floor: with 1-2 results, statistical filters can't work.
    # Pure COSINE scores for irrelevant content are naturally low.
    if len(scores) <= 2 and scores[0] < SINGLE_RESULT_MIN_FLOOR:
        diag.update(single_result_rejected=True, effective_threshold=top + 1,
                     gap_cutoff_index=0, final_count=0)
        return [], diag

    # Multi-signal rejection: BOTH conditions must be true to reject
    # 1. Top score below minimum (0.70)
    # 2. Top score doesn't stand out from mean (top - mean < 0.15)
    # Only with ≥3 results (1-2 results have unreliable normalization)
    if (len(scores) >= 3
        and scores[0] < TOP_SCORE_MINIMUM
        and top_standout < TOP_SCORE_STANDOUT):
        diag.update(multi_signal_rejected=True, effective_threshold=top + 1,
                     gap_cutoff_index=0, final_count=0)
        return [], diag

    # Compression
    if len(scores) >= 3 and spread < SCORE_SPREAD_THRESHOLD:
        diag.update(compression_rejected=True, effective_threshold=top + 1,
                     gap_cutoff_index=0, final_count=0)
        return [], diag

    # Low variance
    if 0 < std_s < 0.02:
        boosted = mean_s + SCORE_LOW_STD_MULTIPLIER * std_s
        diag.update(low_variance_boost=True, boosted_floor=boosted)
        eff = max(top * ADAPTIVE_SCORE_DROP_RATIO, ADAPTIVE_MIN_FLOOR, boosted)
    else:
        eff = max(top * ADAPTIVE_SCORE_DROP_RATIO, ADAPTIVE_MIN_FLOOR)
    diag["effective_threshold"] = eff

    # Gap detection
    largest, largest_idx = 0.0, len(results)
    for i in range(1, len(results)):
        drop = scores[i - 1] - scores[i]
        if drop > ADAPTIVE_GAP_THRESHOLD and drop > largest:
            largest, largest_idx = drop, i
    if largest > 0:
        gap_cutoff = largest_idx
        diag.update(largest_gap=largest, gap_cutoff_index=gap_cutoff)

    filtered = [r for i, r in enumerate(results) if i < gap_cutoff and r["score"] >= eff]
    diag["final_count"] = len(filtered)
    return filtered, diag


# ═══════════════════════════════════════════════════════════════════
# DISPLAY
# ═══════════════════════════════════════════════════════════════════

def print_header(t):
    print(f"\n{'='*70}\n  {t}\n{'='*70}")

def show(results, diag, indent="    "):
    scores = [r["score"] for r in results] if results else []
    s_str = ", ".join(f"{s:.4f}" for s in scores[:10])
    if len(scores) > 10:
        s_str += "..."
    print(f"{indent}Raw={diag['total_raw']} | Spread={diag['score_spread']:.4f} | "
          f"Std={diag['score_std']:.4f} | Standout={diag['top_standout']:.4f} | "
          f"SingleReject={diag['single_result_rejected']} | "
          f"MultiReject={diag['multi_signal_rejected']} | "
          f"Compressed={diag['compression_rejected']} | "
          f"LowVar={diag['low_variance_boost']} | Threshold={diag['effective_threshold']:.4f} | "
          f"Gap@{diag['gap_cutoff_index']}(drop={diag['largest_gap']:.4f}) | "
          f"Final={diag['final_count']}")
    if scores:
        print(f"{indent}Scores: [{s_str}]")

def result_line(idx, r, indent="      "):
    print(f"{indent}{idx}. {r['score']:.4f} | {r['topic'][:35]} | {r['text'][:80]}...")


# ═══════════════════════════════════════════════════════════════════
# TESTS
# ═══════════════════════════════════════════════════════════════════

async def run_test(client, name, query, folder_id=None, expect="some",
                   expect_topic=None, expect_doc=None):
    """Generic test runner."""
    print(f"\n  📝 [{name}] \"{query[:65]}\"")
    if folder_id:
        print(f"     Folder filter: {folder_id[:30]}...")

    raw = await dense_search(client, query, USER_EMAIL, folder_id=folder_id, top_k=20)
    filtered, diag = apply_filtering(raw)
    show(raw, diag)

    # Show top 3 filtered results
    for i, r in enumerate(filtered[:3], 1):
        result_line(i, r)

    # Evaluate
    status = "✅"
    reason = ""
    if expect == "zero" and diag["final_count"] > 0:
        status = "❌ FAIL"
        reason = f"Expected 0 but got {diag['final_count']}"
    elif expect == "some" and diag["final_count"] == 0:
        status = "⚠️ WARN"
        reason = "Expected results but got 0"
    elif expect == "many" and diag["final_count"] < 3:
        status = "⚠️ WARN"
        reason = f"Expected ≥3 but got {diag['final_count']}"

    if expect_topic and filtered:
        matching = [r for r in filtered if expect_topic.lower() in r["topic"].lower()]
        if not matching:
            status = "❌ FAIL"
            reason = f"Expected topic '{expect_topic}' in results"

    if expect_doc and filtered:
        matching = [r for r in filtered if r["document_id"] == expect_doc]
        if not matching:
            status = "❌ FAIL"
            reason = f"Expected doc_id '{expect_doc[:20]}' in results"

    print(f"     {status} → {diag['final_count']} results {f'({reason})' if reason else ''}")
    return status, diag


async def run_all_tests(client: MilvusClient):
    """Run all 12 test scenarios."""
    results = []

    # ── GROUP 1: RELEVANCE (should find results) ──
    print_header("GROUP 1: RELEVANCE TESTS (expect results)")

    r = await run_test(client, "Solar Direct Match",
        "How efficient are modern solar panels and what is their cost?",
        expect="many", expect_topic="Solar")
    results.append(("Solar Direct Match", r[0]))

    r = await run_test(client, "Solar Keyword Match",
        "net metering policy for rooftop photovoltaic systems",
        expect="some", expect_topic="Solar")
    results.append(("Solar Keyword Match", r[0]))

    r = await run_test(client, "Marine Direct Match",
        "coral reef ecosystems and ocean biodiversity",
        expect="many", expect_topic="Marine")
    results.append(("Marine Direct Match", r[0]))

    r = await run_test(client, "Marine Keyword Match",
        "humpback whale migration patterns and feeding behavior",
        expect="some", expect_topic="Marine")
    results.append(("Marine Keyword Match", r[0]))

    # ── GROUP 2: IRRELEVANCE (should get 0 results) ──
    print_header("GROUP 2: IRRELEVANCE TESTS (expect 0 results)")

    r = await run_test(client, "Cooking Recipe",
        "How to make authentic Italian carbonara pasta with pancetta and eggs?",
        expect="zero")
    results.append(("Cooking Recipe", r[0]))

    r = await run_test(client, "Sports Rules",
        "What are the offside rules in professional soccer and how are they enforced?",
        expect="zero")
    results.append(("Sports Rules", r[0]))

    r = await run_test(client, "Medieval History",
        "The political structure of feudal kingdoms in 12th century Europe",
        expect="zero")
    results.append(("Medieval History", r[0]))

    r = await run_test(client, "Fashion Design",
        "haute couture spring collection runway trends for Paris fashion week",
        expect="zero")
    results.append(("Fashion Design", r[0]))

    # ── GROUP 3: FOLDER ISOLATION ──
    print_header("GROUP 3: FOLDER ISOLATION TESTS")

    r = await run_test(client, "Solar in Solar Folder",
        "solar panel efficiency and photovoltaic technology",
        folder_id=TEST_FOLDER_SOLAR, expect="many", expect_topic="Solar")
    results.append(("Solar→Solar Folder", r[0]))

    r = await run_test(client, "Solar in Marine Folder",
        "solar panel efficiency and photovoltaic technology",
        folder_id=TEST_FOLDER_MARINE, expect="zero")
    results.append(("Solar→Marine Folder", r[0]))

    r = await run_test(client, "Marine in Marine Folder",
        "deep sea hydrothermal vents and tube worms",
        folder_id=TEST_FOLDER_MARINE, expect="some", expect_topic="Marine")
    results.append(("Marine→Marine Folder", r[0]))

    r = await run_test(client, "Marine in Solar Folder",
        "deep sea hydrothermal vents and tube worms",
        folder_id=TEST_FOLDER_SOLAR, expect="zero")
    results.append(("Marine→Solar Folder", r[0]))

    # ── GROUP 4: CROSS-DOMAIN CONFUSION ──
    print_header("GROUP 4: CROSS-DOMAIN CONFUSION TESTS")

    r = await run_test(client, "Energy Ambiguous",
        "What is the most efficient way to generate energy from natural sources?",
        expect="some", expect_topic="Solar")
    results.append(("Energy Ambiguous", r[0]))

    r = await run_test(client, "Environment Overlap",
        "environmental impact and carbon dioxide effects on the planet",
        expect="some")  # Could match both — just ensure filtering works
    results.append(("Environment Overlap", r[0]))

    # ── GROUP 5: COMPRESSION DETECTION WITH MORE DATA ──
    print_header("GROUP 5: COMPRESSION DETECTION (with 20 vectors)")

    r = await run_test(client, "Total Nonsense",
        "xylophone manufacturing techniques in ancient Aztec civilization",
        expect="zero")
    results.append(("Total Nonsense", r[0]))

    r = await run_test(client, "Unrelated Science",
        "quantum entanglement teleportation experiments at CERN particle accelerator",
        expect="zero")
    results.append(("Unrelated Science", r[0]))

    # ── GROUP 6: SCORE DISTRIBUTION DEEP DIVE ──
    print_header("GROUP 6: SCORE DISTRIBUTION COMPARISON")

    queries = [
        ("solar panel cost and installation", "Highly Relevant"),
        ("banana smoothie recipe with yogurt", "Totally Irrelevant"),
        ("energy and environmental research", "Partially Relevant"),
    ]
    for q, label in queries:
        print(f"\n  📊 [{label}] \"{q}\"")
        raw = await dense_search(client, q, USER_EMAIL, top_k=20)
        if raw:
            scores = [r["score"] for r in raw]
            std = statistics.pstdev(scores)
            spread = max(scores) - min(scores)
            mean = statistics.mean(scores)
            print(f"     Count={len(scores)} | Max={max(scores):.4f} | Min={min(scores):.4f} | "
                  f"Spread={spread:.4f} | Std={std:.4f} | Mean={mean:.4f}")
            print(f"     Scores: [{', '.join(f'{s:.4f}' for s in scores[:15])}]")

            _, diag = apply_filtering(raw)
            print(f"     → After filtering: {diag['final_count']} results "
                  f"(single_reject={diag['single_result_rejected']}, multi_reject={diag['multi_signal_rejected']}, compressed={diag['compression_rejected']}, lowvar={diag['low_variance_boost']})")

    # ── SUMMARY ──
    print_header("FINAL SUMMARY")

    passed = sum(1 for _, s in results if s == "✅")
    warned = sum(1 for _, s in results if "⚠️" in s)
    failed = sum(1 for _, s in results if "❌" in s)

    for name, status in results:
        print(f"  {status} {name}")

    print(f"\n  📊 Total: {len(results)} tests | "
          f"✅ {passed} passed | ⚠️ {warned} warnings | ❌ {failed} failed")

    return failed


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

async def main():
    print("\n" + "═" * 70)
    print("  MILVUS FILTERING — FULL DATA TEST SUITE (PURE DENSE COSINE)")
    print(f"  User: {USER_EMAIL}")
    print(f"  Collection: {COLLECTION_NAME}")
    print(f"  Solar folder: {TEST_FOLDER_SOLAR}")
    print(f"  Marine folder: {TEST_FOLDER_MARINE}")
    print(f"  Config: floor={ADAPTIVE_MIN_FLOOR}, "
          f"top_min={TOP_SCORE_MINIMUM}, standout={TOP_SCORE_STANDOUT}, "
          f"single_floor={SINGLE_RESULT_MIN_FLOOR}, "
          f"spread={SCORE_SPREAD_THRESHOLD}, gap={ADAPTIVE_GAP_THRESHOLD}")
    print("═" * 70)

    client = get_client()
    failed = 0

    try:
        # Phase 1: Insert test data
        await insert_test_data(client)

        # Phase 2: Run tests
        failed = await run_all_tests(client)

    finally:
        # Phase 3: Always clean up
        await cleanup_test_data(client)

    if failed > 0:
        print(f"\n❌ {failed} test(s) FAILED — review results above")
        sys.exit(1)
    else:
        print(f"\n✅ All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
