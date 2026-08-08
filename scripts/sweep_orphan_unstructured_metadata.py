"""
Maintenance Script: Sweep orphaned unstructured_file_metadata rows.

An "orphan" is a row in ``unstructured_file_metadata`` whose ``document_id``
has no matching ``_id`` in the ``files`` collection. The file-listing service
logs these forever as::

    WARNING - unstructured_file_listing: orphan metadata for document_id=<id>

and skips them on every query. They are produced when a file's ``files`` record
is deleted but its enrichment metadata is not (e.g. legacy deletes from before
the cascade existed, or a partial cascade failure). The delete path has since
been reordered so metadata dies before its file — this script clears the rows
that were orphaned before that fix.

Usage:
    python scripts/sweep_orphan_unstructured_metadata.py            # dry-run (default, no writes)
    python scripts/sweep_orphan_unstructured_metadata.py --apply    # actually delete the orphans

Options:
    --apply        Delete the orphaned rows. Without it, the script only reports.
    --batch-size   How many metadata rows to scan per batch (default: 1000).
"""

import asyncio
import argparse
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vault_env_loader import load_environment_variables
load_environment_variables()

from citra_mongo import get_async_mongo_client, MONGODB_DATABASE

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def sweep(apply: bool = False, batch_size: int = 1000):
    logger.info("=" * 60)
    logger.info("🧹 Orphan unstructured_file_metadata sweep")
    logger.info("=" * 60)
    if not apply:
        logger.info("🔍 DRY RUN — no rows will be deleted (pass --apply to delete)")

    client = get_async_mongo_client()
    db = client[MONGODB_DATABASE]
    logger.info(f"📊 Connected to database: {MONGODB_DATABASE}")

    meta_col = db["unstructured_file_metadata"]
    files_col = db["files"]

    total = await meta_col.count_documents({})
    logger.info(f"📄 Scanning {total} unstructured_file_metadata rows…")

    orphans = []          # list of (mongo _id, document_id, user_id, filename)
    scanned = 0
    batch = []

    async def _check_batch(rows):
        """Given a batch of metadata rows, return those with no files._id match."""
        doc_ids = [r.get("document_id") for r in rows if r.get("document_id")]
        if not doc_ids:
            return []
        existing_cursor = files_col.find({"_id": {"$in": doc_ids}}, {"_id": 1})
        existing = {f["_id"] async for f in existing_cursor}
        return [r for r in rows if r.get("document_id") not in existing]

    cursor = meta_col.find(
        {},
        {"_id": 1, "document_id": 1, "user_id": 1, "filename": 1},
    )
    async for row in cursor:
        batch.append(row)
        scanned += 1
        if len(batch) >= batch_size:
            for r in await _check_batch(batch):
                orphans.append(r)
            batch = []
    if batch:
        for r in await _check_batch(batch):
            orphans.append(r)

    logger.info(f"✅ Scanned {scanned} rows; found {len(orphans)} orphan(s).")

    for r in orphans:
        logger.info(
            "   🔸 orphan: _id=%s document_id=%s user_id=%s filename=%s",
            r.get("_id"), r.get("document_id"), r.get("user_id"), r.get("filename"),
        )

    if not orphans:
        logger.info("🎉 Nothing to clean.")
        return

    if not apply:
        logger.info(f"🔍 DRY RUN — would delete {len(orphans)} orphan(s). Re-run with --apply.")
        return

    orphan_mongo_ids = [r["_id"] for r in orphans]
    result = await meta_col.delete_many({"_id": {"$in": orphan_mongo_ids}})
    logger.info(f"🗑️ Deleted {result.deleted_count} orphan metadata row(s).")


def main():
    parser = argparse.ArgumentParser(description="Sweep orphaned unstructured_file_metadata rows.")
    parser.add_argument("--apply", action="store_true", help="Delete orphans (default: dry-run only).")
    parser.add_argument("--batch-size", type=int, default=1000, help="Rows scanned per batch.")
    args = parser.parse_args()
    asyncio.run(sweep(apply=args.apply, batch_size=args.batch_size))


if __name__ == "__main__":
    main()
