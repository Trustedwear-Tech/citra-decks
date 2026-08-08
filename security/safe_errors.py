"""
Safe Error Responses — prevent internal details from leaking to clients.

Usage:
    from security.safe_errors import safe_http_error
    raise safe_http_error(500, e, logger, context="get_document_metadata")
"""

import logging
from fastapi import HTTPException

# Generic messages by status code — no internal info exposed
_GENERIC_MESSAGES = {
    400: "Bad request",
    401: "Authentication required",
    403: "Access denied",
    404: "Resource not found",
    500: "Internal server error",
}


def safe_http_error(
    status_code: int,
    exc: Exception,
    logger: logging.Logger,
    *,
    context: str = "",
) -> HTTPException:
    """
    Log the real error server-side and return a generic HTTPException to the client.
    """
    prefix = f"[{context}] " if context else ""
    logger.error(f"{prefix}{exc}", exc_info=False)
    detail = _GENERIC_MESSAGES.get(status_code, "Unexpected error")
    return HTTPException(status_code=status_code, detail=detail)
