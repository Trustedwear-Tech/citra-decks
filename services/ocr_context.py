# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

"""
ocr_context — turn pasted-screenshot attachments into LLM context text.

Shared by the presentation/printable composer agent-edit endpoints. Mirrors the
OCR-first pattern already used by quick chat / action chat: each base64 image is
OCR'd (Qwen vision) and wrapped in a delimited ATTACHMENT block, then prepended
to the user's instruction. Per-image failures degrade gracefully so the turn
still succeeds.
"""

import asyncio
import base64
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Max base64 payload per image (~9 MB raw). Matches the quick-chat cap.
MAX_PASTED_IMAGE_B64 = 12 * 1024 * 1024


async def ocr_attachments_to_blocks(
    attachments: Optional[List[Dict[str, Any]]],
    user_id: str = None,
    user_email: str = None,
) -> List[str]:
    """OCR base64 image attachments into delimited context blocks.

    Returns a list of blocks shaped:
        === ATTACHMENT: name ===
        <ocr text or error note>
        === END ATTACHMENT ===

    Non-image attachments are skipped. Per-image failures produce a placeholder
    block (the turn still succeeds; the LLM is told the image couldn't be read).
    """
    from qwen_ocr_proxy import extract_text_from_image

    blocks: List[str] = []
    if not attachments:
        return blocks

    logger.info(f"📋 [COMPOSER_PASTE] Received {len(attachments)} pasted attachment(s)")

    for idx, att in enumerate(attachments, 1):
        name = (att.get("name") or f"clipboard_image_{idx}.png").strip()
        mime_type = att.get("mimeType") or att.get("type") or ""
        b64_data = att.get("base64") or att.get("data") or att.get("content") or ""

        if not isinstance(mime_type, str) or not mime_type.lower().startswith("image/"):
            logger.info(f"📋 [COMPOSER_PASTE] Skipping non-image attachment: {name} ({mime_type})")
            continue

        if not b64_data:
            blocks.append(
                f"=== ATTACHMENT: {name} ===\n[Image could not be processed: no data provided]\n=== END ATTACHMENT ==="
            )
            continue

        # Strip data-URL prefix if present
        if "," in b64_data[:64] and b64_data[:5].lower() == "data:":
            b64_data = b64_data.split(",", 1)[1]

        if len(b64_data) > MAX_PASTED_IMAGE_B64:
            logger.warning(f"⚠️ [COMPOSER_PASTE] Image {name} exceeds size limit ({len(b64_data)} base64 chars)")
            blocks.append(
                f"=== ATTACHMENT: {name} ===\n[Image could not be processed: exceeds maximum size]\n=== END ATTACHMENT ==="
            )
            continue

        try:
            raw_bytes = base64.b64decode(b64_data)
        except Exception as e:
            logger.error(f"❌ [COMPOSER_PASTE_OCR] base64 decode failed for {name}: {e}")
            blocks.append(
                f"=== ATTACHMENT: {name} ===\n[Image could not be processed: invalid encoding]\n=== END ATTACHMENT ==="
            )
            continue

        t0 = time.time()
        try:
            text = await asyncio.to_thread(
                extract_text_from_image,
                raw_bytes,
                filename=name,
                mime_type=mime_type,
                user_id=user_id,
                user_email=user_email or user_id,
            )
            elapsed_ms = int((time.time() - t0) * 1000)
            text = (text or "").strip()
            if text:
                logger.info(f"✅ [COMPOSER_PASTE_OCR] ok: {name} → {len(text)} chars in {elapsed_ms}ms")
                blocks.append(f"=== ATTACHMENT: {name} ===\n{text}\n=== END ATTACHMENT ===")
            else:
                logger.warning(f"⚠️ [COMPOSER_PASTE_OCR] empty result for {name} ({elapsed_ms}ms)")
                blocks.append(
                    f"=== ATTACHMENT: {name} ===\n[Image appears to contain no readable text]\n=== END ATTACHMENT ==="
                )
        except Exception as e:
            elapsed_ms = int((time.time() - t0) * 1000)
            err_msg = str(e)[:200]
            logger.error(f"❌ [COMPOSER_PASTE_OCR] failed for {name} ({elapsed_ms}ms): {err_msg}")
            blocks.append(
                f"=== ATTACHMENT: {name} ===\n[Image could not be processed: {err_msg}]\n=== END ATTACHMENT ==="
            )

    return blocks


async def prepend_ocr_to_instruction(
    instruction: str,
    attachments: Optional[List[Dict[str, Any]]],
    user_id: str = None,
    user_email: str = None,
) -> str:
    """Convenience: OCR attachments and prepend the blocks to `instruction`.

    Returns the original instruction unchanged when there are no usable images.
    """
    blocks = await ocr_attachments_to_blocks(attachments, user_id=user_id, user_email=user_email)
    if not blocks:
        return instruction
    return (
        "\n\n".join(blocks)
        + "\n\n--- USER INSTRUCTION ---\n"
        + (instruction or "")
    )
