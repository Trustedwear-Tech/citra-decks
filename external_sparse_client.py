# """External SPLADE sparse vector client.

# Centralizes calls to the detached SPLADE microservice so the main Lawogic
# service no longer loads heavy SPLADE models in‑process.

# Environment Variables:
#   SPLADE_SERVICE_URL      Base URL of the splade-sparse-service (e.g. http://localhost:7050)
#   SPARSE_TIMEOUT          (optional) request timeout seconds (default 60)
#   SPARSE_BATCH_SIZE       (optional) soft client-side batch size (default 16)
#   DISABLE_INLINE_SPLADE   When '1' (default) prevents any inline model loading attempts

# Return Format:
#   Each vector: {"indices": [...], "values": [...], "token_count": int}

# Failure Handling:
#   - On HTTP / parsing errors we FAIL EARLY and raise exceptions - no fallbacks.
#   - System requires SPLADE service to be operational for proper functioning.
# """

# from __future__ import annotations

# import os
# import logging
# from typing import List, Optional, Dict, Any

# import httpx

# logger = logging.getLogger(__name__)


# def splade_service_enabled() -> bool:
#     url = os.getenv("SPLADE_SERVICE_URL")
#     return bool(url and url.strip())


# def get_splade_service_url() -> Optional[str]:
#     if not splade_service_enabled():
#         return None
#     return os.getenv("SPLADE_SERVICE_URL").rstrip("/")


# def _chunk_list(items: List[Any], size: int) -> List[List[Any]]:
#     return [items[i : i + size] for i in range(0, len(items), size)]


# async def fetch_sparse_vectors_async(
#     texts: List[str],
#     max_tokens: Optional[int] = None,
#     batch_size: Optional[int] = None,
# ) -> List[Dict[str, Any]]:
#     """Async batch fetch of sparse vectors from external service.

#     FAILS EARLY if service unavailable or any request fails.
#     No fallbacks - system requires working SPLADE service.
#     """
#     base_url = get_splade_service_url()
#     if not base_url:
#         raise RuntimeError("❌ SPLADE service URL not configured. Set SPLADE_SERVICE_URL environment variable.")

#     timeout = float(os.getenv("SPARSE_TIMEOUT", "60"))
#     client_batch = batch_size or int(os.getenv("SPARSE_BATCH_SIZE", "16"))

#     results: List[Dict[str, Any]] = []
#     async with httpx.AsyncClient(timeout=timeout) as client:
#         for group in _chunk_list(texts, client_batch):
#             payload = {"texts": group}
#             if max_tokens:
#                 payload["max_tokens"] = max_tokens
#             try:
#                 resp = await client.post(f"{base_url}/sparse/embed", json=payload)
#                 if resp.status_code != 200:
#                     error_text = resp.text or ''
#                     logger.error(
#                         f"❌ SPLADE service error {resp.status_code}: {error_text[:200]}"
#                     )
                    
#                     # Check for batch size limit error and suggest fix
#                     if resp.status_code == 400 and "exceeds MAX_BATCH" in error_text:
#                         logger.error(f"💡 Batch size {len(group)} exceeds server limit. Consider setting SPARSE_BATCH_SIZE environment variable to a smaller value (≤16)")
                    
#                     raise RuntimeError(f"SPLADE service request failed with status {resp.status_code}: {error_text[:200]}")
                    
#                 data = resp.json()
#                 vectors = data.get("vectors", [])
#                 # Validate entries - fail if any are invalid
#                 batch_results = []
#                 for i, v in enumerate(vectors):
#                     if not v:
#                         raise RuntimeError(f"SPLADE service returned null vector at index {i}")
#                     indices = v.get("indices", [])
#                     values = v.get("values", [])
#                     if not indices or not values:
#                         raise RuntimeError(f"SPLADE service returned invalid vector at index {i}: missing indices or values")
#                     batch_results.append({"indices": indices, "values": values})
#                 results.extend(batch_results)
                
#             except httpx.RequestError as e:
#                 raise RuntimeError(f"Failed to connect to SPLADE service: {e}")
#             except Exception as e:
#                 raise RuntimeError(f"SPLADE service call failed: {e}")
                
#     # Validate final result count
#     if len(results) != len(texts):
#         raise RuntimeError(
#             f"SPLADE result length mismatch: input={len(texts)} output={len(results)}"
#         )
#     return results


# def fetch_sparse_vectors(texts: List[str], max_tokens: Optional[int] = None) -> List[Dict[str, Any]]:
#     """Synchronous convenience wrapper (for non-async contexts)."""
#     import anyio

#     return anyio.run(fetch_sparse_vectors_async, texts, max_tokens, None)


# async def fetch_single_sparse(text: str) -> Dict[str, Any]:
#     if not text or not text.strip():
#         raise ValueError("Cannot generate sparse vector for empty text")
#     vectors = await fetch_sparse_vectors_async([text])
#     return vectors[0]
