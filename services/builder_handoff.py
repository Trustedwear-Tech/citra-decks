"""builder_handoff.py — shared chat→builder handoff.

When the LLM (main chat or quick chat) calls the ``make_presentation`` /
``make_report`` tool, it has already gathered its research using the data
tools available to that surface (main chat: vault + MCP + internet; quick
chat: uploaded documents + internet). This helper takes the goal + that
gathered data and:

  1. embeds the gathered research as a NORMAL, visible document into the
     user's selected vault folder (or the default ``documents`` folder when
     nothing is selected),
  2. returns the ``OPEN_BUILDER`` payload the UI uses to open the composer.

The composer's outline + per-slide retrieval then grounds the deliverable on
that same selected vault folder. No temp / internal vault is used — the
embedded research is a regular vault file the user can see and delete.

Routing: ``presentation`` → the presentation composer UI; ``report`` →
the printable (A4) composer UI. The ``builder`` field carries that choice.
"""
from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


async def prepare_builder_handoff(
    *,
    builder: str,                          # "presentation" | "report"
    goal: str,
    data: str,
    count: int,
    user_id: str,
    personal_sa_id: Optional[str],
    org_id: Optional[str] = None,
    user_email: Optional[str] = None,
    selected_folder_ids: Optional[List[str]] = None,
) -> dict:
    """Return the OPEN_BUILDER payload, grounded on the user's SELECTED vault.

    No temp / internal vault is used. The freshly-gathered research (``data``)
    is embedded as a NORMAL, visible vault document into the user's selected
    folder (the first one), so:

      * the composer grounds the deck/report on the SAME vault folder the user
        picked — outline AND every slide/page retrieve from it;
      * the research file shows up in the vault folder UI like any upload; and
      * the user can DELETE it afterwards if they don't want to keep it.

    If no folder is selected (e.g. quick chat, which has no folder picker), the
    research lands in the user's default ``documents`` folder, which is also a
    real, visible folder.

    Embedding uses the same pipeline as a normal vault upload (S3 + Milvus
    chunk embeddings + files-registry entry), so retrieval and the delete path
    treat it identically to any other document.

    Best-effort by design — if the embed fails, the build still opens grounded
    on the selected folder(s) rather than erroring the turn.

    Returns the ``OPEN_BUILDER`` event payload:
    ``{builder, goal, slide_count, folder_ids}``.
    """
    # User's selected vault folders are the grounding source.
    folder_ids: List[str] = [f for f in (selected_folder_ids or []) if f]

    # Target folder for the research doc: the first selected folder, or the
    # user's default visible folder when nothing is selected.
    target_folder = folder_ids[0] if folder_ids else "documents"
    if not folder_ids:
        folder_ids = [target_folder]

    # doc_type drives the prefetch_corpus filename/source tagging only.
    doc_type = "presentation" if builder == "presentation" else "report"

    # Embed the gathered research into the selected vault folder as a normal,
    # visible, user-deletable document.
    embedded_count = 0
    if data and data.strip():
        try:
            from services.internet_prefetch import prefetch_corpus
            embedded = await prefetch_corpus(
                corpus=[{"title": (goal[:120] or "Research"), "text": data}],
                doc_type=doc_type,
                user_id=user_id,
                folder_id=target_folder,
                user_email=user_email,
            )
            embedded_count = len(embedded)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[builder_handoff] research embed failed (non-fatal): %s", exc)

    logger.info(
        "[builder_handoff] builder=%s grounding folder_ids=%s "
        "(research_docs=%d embedded into %s)",
        builder, folder_ids, embedded_count, target_folder,
    )

    return {
        "builder": builder,
        "goal": goal,
        # The UI reads `slide_count` for both surfaces (page count for reports).
        "slide_count": count,
        "folder_ids": folder_ids,
    }
