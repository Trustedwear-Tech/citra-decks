"""
Document Proxy API
Provides same-origin streaming URLs for documents (especially PDFs) to avoid S3 CORS and forced downloads.
"""

import logging
import os
import re
from typing import Optional
from urllib.parse import quote

import jwt
import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from citra_auth import get_secure_user_id
from citra_mongo import get_sync_database
from bucket import generate_download_url

router = APIRouter(prefix="/api/pdfstreaming", tags=["Document Proxy"])
logger = logging.getLogger(__name__)


def _extract_s3_key(s3_url: str) -> str:
    """Convert an S3 URL to a bucket key, tolerating multiple URL styles."""
    if not s3_url:
        return ""
    if ".amazonaws.com/" in s3_url:
        return s3_url.split(".amazonaws.com/", 1)[-1]
    if s3_url.startswith("s3://"):
        return s3_url.split("s3://", 1)[-1]
    return s3_url.lstrip("/")


def _safe_filename(file_record: dict, document_id: str) -> str:
    name = file_record.get("filename") or file_record.get("topic_or_filename") or document_id
    ext = file_record.get("file_extension")
    if ext and not name.lower().endswith(ext.lower()):
        name = f"{name}{ext if ext.startswith('.') else f'.{ext}'}"
    # Strip characters that could cause header injection (CRLF, quotes, null bytes)
    name = re.sub(r'[\r\n\x00"\\/]', '_', name)
    return name


def _content_disposition(filename: str, disposition: str = "inline") -> str:
    """Build a Content-Disposition header value safe for non-ASCII filenames.
    Uses RFC 5987 filename*=UTF-8'' for Unicode names with an ASCII fallback."""
    try:
        filename.encode('latin-1')
        # Pure ASCII/latin-1 — simple header is fine
        return f'{disposition}; filename="{filename}"'
    except UnicodeEncodeError:
        # Non-ASCII: provide ASCII fallback + RFC 5987 UTF-8 encoded name
        ascii_fallback = filename.encode('ascii', 'replace').decode('ascii')
        utf8_encoded = quote(filename, safe='')
        return f"{disposition}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{utf8_encoded}"


async def _get_file_record(document_id: str, user_id: str) -> Optional[dict]:
    db = get_sync_database()
    record = db["files"].find_one({"_id": document_id, "user_id": user_id})
    if not record:
        # Shared access fallback: find the document by _id only, then verify vault-level access
        shared_record = db["files"].find_one({"_id": document_id})
        if shared_record:
            doc_folder_id = shared_record.get("folder_id")
            if doc_folder_id:
                try:
                    from services.authorization_service import get_authorization_service
                    auth_service = get_authorization_service()
                    access_result = await auth_service.check_access(
                        user_id=user_id,
                        resource_id=doc_folder_id,
                        resource_type="vault",
                        required_permission="read"
                    )
                    if access_result.get("allowed"):
                        logger.info(f"✅ [PDF_PROXY] Shared access granted for document {document_id} via vault {doc_folder_id}")
                        record = shared_record
                except Exception as auth_err:
                    logger.warning(f"⚠️ [PDF_PROXY] Error checking shared access: {auth_err}")
            else:
                logger.warning(f"⚠️ [PDF_PROXY] Shared document {document_id} has no folder_id — skipping auth check")
    return record


def _resolve_user_id(request: Request, token_param: Optional[str]) -> str:
    """Resolve user id from Authorization header or fallback token query param."""
    try:
        return get_secure_user_id(request)
    except Exception:
        pass

    if token_param:
        try:
            jwt_secret = os.getenv("JWT_SECRET")
            payload = jwt.decode(jwt=token_param, key=jwt_secret, algorithms=["HS256"])
            return payload.get("user_id") or payload.get("sub") or payload.get("email")
        except Exception as exc:
            logger.warning(f"🔒 Invalid token parameter: {exc}")

    raise HTTPException(status_code=401, detail="Authentication required")


@router.get("/{document_id}/proxy")
async def get_document_proxy(document_id: str, request: Request, token: Optional[str] = None):
    """Return a same-origin proxy URL for a document so the web app can render PDFs inline."""
    user_id = _resolve_user_id(request, token)
    file_record = await _get_file_record(document_id, user_id)
    if not file_record:
        raise HTTPException(status_code=404, detail="Document not found or access denied")

    s3_url = file_record.get("s3_url")
    if not s3_url:
        raise HTTPException(status_code=404, detail="Document storage location missing")

    s3_key = _extract_s3_key(s3_url)
    if not s3_key:
        raise HTTPException(status_code=500, detail="Unable to resolve document storage key")

    # Ensure the signed URL exists (validated up-front), but return a backend stream URL for CORS safety
    try:
        _ = generate_download_url(s3_key, expiry_seconds=1800)
    except Exception as exc:  # generate_download_url already logs
        logger.error(f"❌ Failed to presign document {document_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to generate document URL")

    # Stream through the renamed pdfstreaming router (avoids stale /api/documents path)
    # Use X-Forwarded-Proto to ensure HTTPS in production behind proxies
    proto = request.headers.get("X-Forwarded-Proto", "http")
    host = request.headers.get("Host", str(request.base_url.hostname))
    # Force HTTPS for production domains to prevent mixed content errors
    if "api.citra-ai.com" in host or "citra-ai.com" in host:
        proto = "https"
    # Honor reverse-proxy prefixes (e.g., /citra-ai) so generated URLs stay valid in prod
    forwarded_prefix = request.headers.get("X-Forwarded-Prefix")
    root_path = forwarded_prefix or request.scope.get("root_path", "") or ""
    if root_path and not root_path.startswith("/"):
        root_path = f"/{root_path}"
    root_path = root_path.rstrip("/")

    base_url = f"{proto}://{host}{root_path}"
    stream_url = f"{base_url}/api/pdfstreaming/{document_id}/proxy/stream"
    if token:
        stream_url = f"{stream_url}?token={token}"
    filename = _safe_filename(file_record, document_id)
    content_type = file_record.get("content_type", "application/pdf")

    return JSONResponse(
        content={
            "success": True,
            "proxy_url": stream_url,
            "download_url": stream_url,
            "filename": filename,
            "content_type": content_type,
        }
    )


@router.get("/{document_id}/proxy/stream")
async def stream_document(document_id: str, request: Request, token: Optional[str] = None):
    """Stream the document through the backend with CORS headers for safe inline rendering."""
    user_id = _resolve_user_id(request, token)
    file_record = await _get_file_record(document_id, user_id)
    if not file_record:
        raise HTTPException(status_code=404, detail="Document not found or access denied")

    s3_key = _extract_s3_key(file_record.get("s3_url", ""))
    if not s3_key:
        raise HTTPException(status_code=404, detail="Document storage location missing")

    try:
        signed_url = generate_download_url(s3_key, expiry_seconds=1800)
    except Exception as exc:
        logger.error(f"❌ Failed to presign document {document_id} for streaming: {exc}")
        raise HTTPException(status_code=500, detail="Failed to generate document URL")

    upstream = requests.get(signed_url, stream=True, timeout=60)
    if upstream.status_code >= 400:
        logger.error(f"❌ Upstream fetch failed for {document_id}: {upstream.status_code}")
        raise HTTPException(status_code=upstream.status_code, detail="Failed to fetch document")

    content_type = upstream.headers.get("Content-Type", file_record.get("content_type", "application/pdf"))
    filename = _safe_filename(file_record, document_id)

    # CORS: validate origin against allowlist instead of reflecting arbitrary origin
    _ALLOWED_ORIGINS = {
        "https://citra-ai.com",
    }
    if os.getenv("ENVIRONMENT", "production") != "production":
        _ALLOWED_ORIGINS.update({"http://localhost:8081", "http://127.0.0.1:8081"})

    origin = request.headers.get("origin")
    cors_origin = origin if origin in _ALLOWED_ORIGINS else "https://citra-ai.com"

    headers = {
        "Access-Control-Allow-Origin": cors_origin,
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Expose-Headers": "Content-Disposition",
        "Content-Disposition": _content_disposition(filename, "inline"),
        "X-Frame-Options": "ALLOWALL",
        "Vary": "Origin",
    }
    if origin in _ALLOWED_ORIGINS:
        headers["Access-Control-Allow-Credentials"] = "true"

    return StreamingResponse(
        upstream.iter_content(chunk_size=8192),
        media_type=content_type,
        headers=headers,
    )
