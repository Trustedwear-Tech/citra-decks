"""Smoke tests for upload-time enricher + chat-time scorer.
Run with: python test_metadata_smoke.py
"""
import asyncio
import json
from unittest.mock import patch

from services.file_metadata_enricher import enrich_file_metadata, _parse_response, EMPTY_RESULT
from services.file_relevance_scorer import (
    score_files_against_query,
    CandidateFile,
    _parse_response as scorer_parse,
)


def test_enricher_parse():
    ok = _parse_response(json.dumps({
        "summary": "Q3 2025 audit findings on SOC2 controls.",
        "doc_type": "report",
        "semantic_tags": ["audit", "soc2", "access-control"],
        "key_entities": ["Acme Corp", "FinOps"],
    }))
    assert ok["doc_type"] == "report"
    assert "audit" in ok["semantic_tags"]
    print("[OK] enricher parse_response")

    empty = _parse_response("not json")
    assert empty == dict(EMPTY_RESULT)
    print("[OK] enricher handles bad JSON")

    fenced = "```json\n" + json.dumps({"summary":"x","doc_type":"y","semantic_tags":[],"key_entities":[]}) + "\n```"
    parsed = _parse_response(fenced)
    assert parsed["doc_type"] == "y"
    print("[OK] enricher handles fenced JSON")

    # Validation clipping
    bloated = json.dumps({
        "summary": "x" * 1000,
        "doc_type": "y" * 200,
        "semantic_tags": ["t" + str(i) for i in range(50)],
        "key_entities": ["e" + str(i) for i in range(50)],
    })
    p = _parse_response(bloated)
    assert len(p["summary"]) <= 400
    assert len(p["doc_type"]) <= 60
    assert len(p["semantic_tags"]) <= 10
    assert len(p["key_entities"]) <= 10
    print("[OK] enricher clips oversize fields")


async def test_enricher_mock_llm():
    fake = json.dumps({
        "summary": "A 2024 vendor contract with mutual indemnification.",
        "doc_type": "contract",
        "semantic_tags": ["contract", "vendor", "indemnification"],
        "key_entities": ["Acme", "Beta Inc."],
    })
    with patch("llm_oss.llm_call", return_value=fake):
        out = await enrich_file_metadata(
            filename="vendor_msa.pdf",
            file_type=".pdf",
            extracted_text="This Master Services Agreement is entered into...",
            user_id="u1",
        )
    assert out["doc_type"] == "contract"
    assert "vendor" in out["semantic_tags"]
    print("[OK] enricher end-to-end with mocked LLM")


async def test_enricher_llm_failure():
    # LLM raises -> empty result (never raises)
    def boom(**kw):
        raise RuntimeError("LLM down")
    with patch("llm_oss.llm_call", side_effect=boom):
        out = await enrich_file_metadata(
            filename="x.pdf", file_type=".pdf", extracted_text="hello", user_id="u1",
        )
    assert out == dict(EMPTY_RESULT)
    print("[OK] enricher swallows LLM errors")

    # LLM returns garbage -> empty result
    with patch("llm_oss.llm_call", return_value="totally not json"):
        out = await enrich_file_metadata(
            filename="x.pdf", file_type=".pdf", extracted_text="hello", user_id="u1",
        )
    assert out == dict(EMPTY_RESULT)
    print("[OK] enricher swallows garbage response")


def test_scorer_parse():
    candidates = [
        CandidateFile(document_id="d1", filename="audit.pdf"),
        CandidateFile(document_id="d2", filename="cat.jpg"),
        CandidateFile(document_id="d3", filename="contract.pdf"),
    ]
    raw = json.dumps({"scores": [
        {"document_id": "d1", "score": 0.95, "reason": "exact match for audit"},
        {"document_id": "d2", "score": 0.05, "reason": "unrelated"},
        {"document_id": "d3", "score": 0.40, "reason": "weakly related"},
    ]})
    parsed = scorer_parse(raw, candidates)
    assert len(parsed) == 3
    by_id = {p.document_id: p for p in parsed}
    assert by_id["d1"].score == 0.95
    assert by_id["d2"].score == 0.05
    print("[OK] scorer parse_response")

    # Bad doc_id ignored
    raw2 = json.dumps({"scores": [
        {"document_id": "ghost", "score": 1.0, "reason": "..."},
        {"document_id": "d1", "score": 0.7, "reason": "ok"},
    ]})
    parsed2 = scorer_parse(raw2, candidates)
    assert len(parsed2) == 1
    assert parsed2[0].document_id == "d1"
    print("[OK] scorer drops unknown document_ids")

    # Out-of-range score clamped
    raw3 = json.dumps({"scores": [
        {"document_id": "d1", "score": 1.5, "reason": "x"},
        {"document_id": "d2", "score": -0.5, "reason": "x"},
    ]})
    parsed3 = scorer_parse(raw3, candidates)
    by_id3 = {p.document_id: p for p in parsed3}
    assert by_id3["d1"].score == 1.0
    assert by_id3["d2"].score == 0.0
    print("[OK] scorer clamps scores to [0,1]")


async def test_scorer_e2e_mock():
    candidates = [
        CandidateFile(document_id="d1", filename="compliance_review.pdf",
                      doc_type="report", summary="Q3 SOC2 audit findings",
                      semantic_tags=["audit", "soc2"], key_entities=["Acme"]),
        CandidateFile(document_id="d2", filename="cat_meme.jpg",
                      doc_type="image", summary="A funny cat picture",
                      semantic_tags=["cat", "meme"], key_entities=[]),
        CandidateFile(document_id="d3", filename="vendor_contract.pdf",
                      doc_type="contract", summary="Master services agreement",
                      semantic_tags=["contract"], key_entities=["Beta Inc."]),
    ]
    fake = json.dumps({"scores": [
        {"document_id": "d1", "score": 0.92, "reason": "directly addresses audit"},
        {"document_id": "d2", "score": 0.02, "reason": "completely unrelated"},
        {"document_id": "d3", "score": 0.30, "reason": "tangentially related"},
    ]})
    # Bypass cache by stubbing redis lookup
    with patch("services.file_relevance_scorer._cache_get", return_value=None), \
         patch("services.file_relevance_scorer._cache_set"), \
         patch("llm_oss.llm_call", return_value=fake):
        results = await score_files_against_query(
            query="show me the audit doc",
            candidates=candidates,
            user_id="u1",
            folder_ids=["f1"],
            threshold=0.5,
        )
    assert len(results) == 1
    assert results[0].document_id == "d1"
    print("[OK] scorer e2e: only files >= threshold returned")

    # Empty query / candidates
    empty1 = await score_files_against_query(query="", candidates=candidates, user_id="u")
    assert empty1 == []
    empty2 = await score_files_against_query(query="x", candidates=[], user_id="u")
    assert empty2 == []
    print("[OK] scorer short-circuits empty inputs")


async def test_scorer_llm_failure():
    from services.file_relevance_scorer import ScorerUnavailable

    candidates = [CandidateFile(document_id="d1", filename="x.pdf")]
    with patch("services.file_relevance_scorer._cache_get", return_value=None), \
         patch("services.file_relevance_scorer._cache_set"), \
         patch("llm_oss.llm_call", side_effect=RuntimeError("down")):
        try:
            await score_files_against_query(query="q", candidates=candidates, user_id="u1")
            raised = False
        except ScorerUnavailable:
            raised = True
    assert raised, "scorer should raise ScorerUnavailable on LLM failure"
    print("[OK] scorer raises ScorerUnavailable on LLM failure")


async def main():
    test_enricher_parse()
    await test_enricher_mock_llm()
    await test_enricher_llm_failure()
    test_scorer_parse()
    await test_scorer_e2e_mock()
    await test_scorer_llm_failure()
    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
