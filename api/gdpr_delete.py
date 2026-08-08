"""
GDPR Article 17 — Bulk User Data Deletion Endpoint

DELETE /api/v2/user/delete-all-data

Permanently removes ALL data belonging to a user across every MongoDB
collection in Citra-Service, plus their S3 files and Milvus vector
embeddings.

This endpoint requires a valid JWT token. The Citra-User-Service
delete-account handler forwards the user's original auth token so
the middleware authenticates the request normally.
"""

import os
import logging
from typing import Any, Dict, List, Tuple
from fastapi import APIRouter, Request, HTTPException, status
from pydantic import BaseModel
from citra_auth import get_secure_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/user", tags=["GDPR User Data Deletion"])


class DeleteUserDataRequest(BaseModel):
    email: str
    confirmation: str  # Must be "DELETE"


def _get_user_email(request: Request, body: DeleteUserDataRequest) -> str:
    """
    Resolve the authenticated user's email from the JWT token.

    The middleware verifies the JWT and sets `request.state.authenticated`.
    We use `get_secure_user_id()` so the caller cannot spoof the email
    via the request body — the `body.email` is IGNORED.
    """
    is_jwt_authenticated = getattr(request.state, "authenticated", False)

    if not is_jwt_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: provide a valid JWT token",
        )

    user_id = get_secure_user_id(request)
    logger.info(f"🔒 [GDPR-DELETE] Authenticated via JWT for {user_id}")
    return user_id


# ────────────────────────────────────────────────────────
# All user-data collections and their email/user_id field
# ────────────────────────────────────────────────────────
# Format: (collection_name, field_name)
# field_name is the field that stores the user identifier (email)
USER_DATA_COLLECTIONS = [
    # ── Chat ──
    ("ChatSessions", "user_id"),
    ("MessagePairs", "user_id"),
    ("chat_history", "user_id"),

    # ── Documents & Files ──
    ("files", "user_id"),
    ("documents", "user_id"),
    ("documents_v2", "user_id"),
    ("document_chunked", "user_id"),
    ("document_chunked_metadata", "user_id"),
    ("chunks_v2", "user_id"),
    ("milvus_chunks", "user_id"),
    ("citra_ai_chunks", "user_id"),
    ("document_templates", "user_id"),

    # ── Notes ──
    ("Notes", "user_id"),

    # ── Audio / Video ──
    ("audio_transcripts", "user_id"),
    ("transcripts", "user_id"),
    ("video_transcripts", "user_id"),
    ("video_transcriptions", "user_id"),

    # ── Presentations & Printables ──
    ("presentations", "user_id"),
    ("printables", "user_id"),
    ("composer_reports", "user_id"),
    ("diagrams", "user_id"),

    # ── Projects ──
    ("projects", "user_id"),
    ("project_backups", "user_id"),

    # ── Folders ──
    ("folders", "user_id"),

    # ── Pages (Notion-style) ──
    ("pages", "user_id"),
    ("page_blocks", "user_id"),
    ("page_databases", "user_id"),

    # ── Knowledge Graph ──
    ("kg_nodes", "user_id"),
    ("kg_edges", "user_id"),

    # ── Resources & Sharing ──
    ("resources", "user_id"),
    ("public_shares", "user_id"),
    ("shared_with_me", "user_id"),
    ("resource_permissions", "user_id"),
    ("vault_shares", "owner_email"),

    # ── Workflows ──
    # INTENTIONALLY EXCLUDED from GDPR user-deletion. The IT workflow surface
    # is ORG-owned, not user-owned: workflows, their saved connections,
    # executions, approvals and templates belong to the org/IT team and are
    # shared across it (see citra-workflow _require_workflow_access /
    # _same_org_or_super). `user_id` on these docs is only `created_by`
    # provenance — deleting the person who happened to create a connection or
    # workflow must NOT wipe shared org infrastructure. Removal/transfer of
    # org resources is an org-admin lifecycle action, not a personal-data
    # erasure. (Collections deliberately omitted: Workflows,
    # WorkflowConnections, WorkflowExecutions, WorkflowApprovals, UserTemplates.)

    # ── Structured file metadata ──
    ("structured_file_metadata", "user_id"),
    ("unstructured_file_metadata", "user_id"),

    # ── Billing / Usage ──
    ("userusages", "user_id"),
    ("credittransactions", "user_id"),

    # ── Personas ──
    ("user_personas", "user_id"),

    # ── Teams (user-owned) ──
    ("teams", "owner_email"),
    ("team_members", "user_email"),
    ("team_invitations", "email"),
    ("workspace_members", "user_email"),
    ("workspaces", "owner_email"),

    # ── Concept Maps ──
    ("concept_maps", "user_id"),
    ("document_concept_maps", "user_id"),
    ("folder_concept_maps", "user_id"),
    ("device_concept_maps", "user_id"),

    # ── Audit & Analytics ──
    ("authorization_audit_log", "user_id"),
]


@router.delete("/delete-all-data")
async def delete_all_user_data(request: Request, body: DeleteUserDataRequest) -> Dict[str, Any]:
    """
    Permanently delete ALL data for a user across every collection.
    Requires { "confirmation": "DELETE" } in the request body.
    """
    if body.confirmation != "DELETE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='You must send {"confirmation": "DELETE"} to confirm deletion',
        )

    user_email = _get_user_email(request, body)
    logger.warning(f"🗑️ [GDPR-DELETE] Starting full data deletion for: {user_email}")

    # Get async MongoDB client
    try:
        from citra_mongo import get_async_mongo_client, MONGODB_DATABASE
        client = get_async_mongo_client()
        db = client[MONGODB_DATABASE]
    except Exception as e:
        logger.error(f"🗑️ [GDPR-DELETE] Failed to connect to MongoDB: {e}")
        raise HTTPException(status_code=500, detail="Database connection failed")

    results: Dict[str, Any] = {}
    total_deleted = 0

    # ── 1. Delete from all MongoDB collections ──
    for collection_name, field_name in USER_DATA_COLLECTIONS:
        try:
            collection = db[collection_name]
            delete_result = await collection.delete_many({field_name: user_email})
            count = delete_result.deleted_count
            results[collection_name] = {"deleted": count, "status": "ok"}
            total_deleted += count
            if count > 0:
                logger.info(f"🗑️ [GDPR-DELETE] {collection_name}: deleted {count} document(s)")
        except Exception as e:
            results[collection_name] = {"deleted": 0, "status": "error", "error": str(e)}
            logger.error(f"🗑️ [GDPR-DELETE] {collection_name}: error — {e}")

    # ── 2. Also try to delete with email field variants ──
    # Some collections might use 'email' instead of 'user_id'
    email_field_collections = [
        ("shared_with_me", "shared_with_email"),
        ("team_invitations", "invited_by"),
    ]
    for collection_name, alt_field in email_field_collections:
        try:
            collection = db[collection_name]
            alt_result = await collection.delete_many({alt_field: user_email})
            if alt_result.deleted_count > 0:
                existing = results.get(collection_name, {"deleted": 0, "status": "ok"})
                existing["deleted"] = existing.get("deleted", 0) + alt_result.deleted_count
                results[collection_name] = existing
                total_deleted += alt_result.deleted_count
        except Exception:
            pass  # Already handled in main loop

    # ── 3. Delete bucket files ──
    # Uses the shared bucket client and config from bucket.py to ensure
    # consistent credentials (BUCKET_*) and bucket name (BUCKET_NAME).
    # User files are stored under:
    #   {env}/{sanitized_email}/...  (documents, audio, video)
    #   pages/{user_email}/...       (page builder images & diagrams)
    s3_deleted = 0
    try:
        from bucket import _get_client, get_config, get_environment_prefix
        from utils import sanitize_container_name

        s3_bucket, _ = get_config()
        s3 = _get_client()
        env_prefix = get_environment_prefix()
        sanitized_email = sanitize_container_name(user_email)

        # Two prefix patterns used across the codebase:
        #  1) {env}/{sanitized_email}/  — documents, audio, video files
        #  2) pages/{user_email}/       — page builder images & diagrams
        prefixes_to_delete = [
            f"{env_prefix}/{sanitized_email}/",
            f"pages/{user_email}/",
        ]

        for prefix in prefixes_to_delete:
            try:
                paginator = s3.get_paginator("list_objects_v2")
                s3_pages = paginator.paginate(Bucket=s3_bucket, Prefix=prefix)

                objects_to_delete = []
                for page in s3_pages:
                    for obj in page.get("Contents", []):
                        objects_to_delete.append({"Key": obj["Key"]})

                # Delete in batches of 1000 (S3 API limit)
                for i in range(0, len(objects_to_delete), 1000):
                    batch = objects_to_delete[i : i + 1000]
                    s3.delete_objects(Bucket=s3_bucket, Delete={"Objects": batch})
                    s3_deleted += len(batch)

                if objects_to_delete:
                    logger.info(f"🗑️ [GDPR-DELETE] S3 prefix '{prefix}': deleted {len(objects_to_delete)} file(s)")
            except Exception as prefix_err:
                logger.error(f"🗑️ [GDPR-DELETE] S3 prefix '{prefix}' error: {prefix_err}")

        results["s3_files"] = {"deleted": s3_deleted, "status": "ok"}
        logger.info(f"🗑️ [GDPR-DELETE] S3 total: deleted {s3_deleted} file(s)")
    except Exception as e:
        results["s3_files"] = {"deleted": 0, "status": "error", "error": str(e)}
        logger.error(f"🗑️ [GDPR-DELETE] S3 deletion error: {e}")

    # ── 4. Delete Milvus/Zilliz vector embeddings ──
    # Uses MilvusClient API (same as rest of codebase) via config/milvus_config.py.
    # Supports both self-hosted Milvus (MILVUS_URI) and Zilliz Cloud (ZILLIZ_CLOUD_URI).
    # Self-hosted Milvus does NOT require an API key — token can be empty.
    # Targets the user-data collection where embeddings are stored:
    #   - citra      (MILVUS_COLLECTION)           — vault documents, notes, audio, pages
    milvus_deleted = 0
    milvus_details: Dict[str, Any] = {}
    try:
        from config.milvus_config import get_milvus_client

        # Check either self-hosted (MILVUS_URI) or cloud (ZILLIZ_CLOUD_URI)
        milvus_uri = os.getenv("MILVUS_URI", "") or os.getenv("ZILLIZ_CLOUD_URI", "")

        if milvus_uri:
            milvus_client = get_milvus_client()

            # The user-data collection (same env var as rest of codebase)
            target_collections = [
                os.getenv("MILVUS_COLLECTION", "citra"),
            ]

            # Escape double-quotes in email to prevent filter injection
            safe_email = user_email.replace('"', '\\"')

            for coll_name in target_collections:
                try:
                    # All 3 collections use "user_id" field to store the user's email
                    result = milvus_client.delete(
                        collection_name=coll_name,
                        filter=f'user_id == "{safe_email}"',
                    )
                    count = result.get("delete_count", 0) if isinstance(result, dict) else 0
                    milvus_deleted += count
                    milvus_details[coll_name] = {"deleted": count, "status": "ok"}
                    logger.info(f"🗑️ [GDPR-DELETE] Milvus '{coll_name}': deleted {count} vector(s)")
                except Exception as coll_err:
                    milvus_details[coll_name] = {"deleted": 0, "status": "error", "error": str(coll_err)}
                    logger.warning(f"🗑️ [GDPR-DELETE] Milvus collection '{coll_name}': {coll_err}")

            results["milvus_vectors"] = {"deleted": milvus_deleted, "status": "ok", "collections": milvus_details}
            logger.info(f"🗑️ [GDPR-DELETE] Milvus total: deleted {milvus_deleted} vector(s)")
        else:
            results["milvus_vectors"] = {"deleted": 0, "status": "skipped", "reason": "Neither MILVUS_URI nor ZILLIZ_CLOUD_URI is configured"}
    except ImportError:
        results["milvus_vectors"] = {"deleted": 0, "status": "skipped", "reason": "pymilvus not installed"}
    except Exception as e:
        results["milvus_vectors"] = {"deleted": 0, "status": "error", "error": str(e)}
        logger.error(f"🗑️ [GDPR-DELETE] Milvus deletion error: {e}")

    # ── 5. Flush Redis cache entries for this user ──
    redis_deleted = 0
    try:
        from citra_cache import CacheManager
        cache = CacheManager()
        if cache.use_redis:
            # Delete user-keyed cache entries (quick-chat sessions, etc.)
            user_patterns = [
                f"qc:user_session:{user_email}",
                f"*:{user_email}:*",
                f"*:{user_email}",
            ]
            for pattern in user_patterns:
                try:
                    if "*" in pattern:
                        matching_keys = cache.keys(pattern)
                        if matching_keys:
                            redis_deleted += cache.delete(*matching_keys)
                    else:
                        redis_deleted += cache.delete(pattern)
                except Exception as pat_err:
                    logger.warning(f"🗑️ [GDPR-DELETE] Redis pattern '{pattern}': {pat_err}")

            results["redis_cache"] = {"deleted": redis_deleted, "status": "ok"}
            logger.info(f"🗑️ [GDPR-DELETE] Redis: deleted {redis_deleted} key(s)")
        else:
            results["redis_cache"] = {"deleted": 0, "status": "skipped", "reason": "Redis not connected"}
    except Exception as e:
        results["redis_cache"] = {"deleted": 0, "status": "error", "error": str(e)}
        logger.error(f"🗑️ [GDPR-DELETE] Redis cleanup error: {e}")

    logger.warning(
        f"🗑️ [GDPR-DELETE] Completed for {user_email}: "
        f"{total_deleted} MongoDB docs + {s3_deleted} S3 files + {milvus_deleted} Milvus vectors + {redis_deleted} Redis keys"
    )

    return {
        "success": True,
        "message": f"All data for {user_email} has been permanently deleted",
        "summary": {
            "mongodb_documents_deleted": total_deleted,
            "s3_files_deleted": s3_deleted,
            "milvus_vectors_deleted": milvus_deleted,
            "redis_keys_deleted": redis_deleted,
        },
        "details": results,
    }


# ════════════════════════════════════════════════════════════════════════
# Phase H — admin-driven personal-content audit + bulk apply
# ════════════════════════════════════════════════════════════════════════
#
# Workflows + smart-apps moved to SA-only ownership and are handled by
# the admin-delete picker in user-service. Everything else a user makes
# (presentations, reports, notes, diagrams, pages, etc.) still has a
# raw `user_id` field on it. When the admin deletes alice, these docs
# would be orphaned unless we explicitly do something.
#
# Three reasonable bulk policies the admin can choose:
#   - "keep"               : leave the docs in place, owner still alice
#                             (useful when the company wants to preserve
#                             her work for audit / future excavation)
#   - "transfer_to_admin"  : rewrite user_id → the admin's own email
#                             (the admin becomes responsible for them)
#   - "delete"             : permanently remove (same path as GDPR delete)
#
# "Content-class" buckets group dozens of collections into a small UI:
#   - documents          (presentations, printables, reports, diagrams)
#   - notes              (Notes, pages, page_blocks, page_databases)
#   - knowledge          (kg_nodes, kg_edges, concept_maps)
# ALL PERSONAL CONTENT IS PRIVATE.
#
# Admin offboarding gets ZERO per-bucket policy choices for personal-output
# resources. Per the privacy rule:
#
#   "Presentations, printables, diagrams, reports, mindmaps, notes,
#    pages, knowledge graphs, media transcripts, chat history, projects,
#    folders + files + chunks, sharing metadata, S3 uploads — all of it
#    is personal data owned by the user's Personal SA. Admin never sees
#    counts or contents. When a user is deleted, everything cascades
#    silently with their Personal SA."
#
# CONTENT_BUCKETS is left as an empty dict for back-compat with the
# admin endpoints below (they return empty results) and the UI
# (DeleteUserScreen.js conditionally renders the Personal-content
# section only when buckets is non-empty — so it gracefully disappears).
# The Worker's PERSONAL_COLLECTIONS is the authoritative wipe list.
CONTENT_BUCKETS: Dict[str, List[Tuple[str, str]]] = {}


# ── Personal collections cascade-deleted with the user ──────────────────────
#
# Authoritative list of EVERY personal-content collection. Mirrored by
# Citra-Worker/handlers/inheritance_handlers.py PERSONAL_COLLECTIONS —
# the worker actually performs the wipe, this constant is kept here so
# both services stay in sync when new collections are added.
#
# Folder _ids must be captured BEFORE the folders are deleted so the
# vault_shares cascade (keyed by `vault_id` = folder _id) finds them.
PRIVATE_PERSONAL_COLLECTIONS = [
    # Presentation-family + templates
    ("presentations", "user_id"),
    ("printables", "user_id"),
    ("composer_reports", "user_id"),
    ("diagrams", "user_id"),
    ("document_templates", "user_id"),
    # Notes / Pages
    ("Notes", "user_id"),
    ("pages", "user_id"),
    ("page_blocks", "user_id"),
    ("page_databases", "user_id"),
    # Knowledge graph + concept maps
    ("kg_nodes", "user_id"),
    ("kg_edges", "user_id"),
    ("concept_maps", "user_id"),
    ("document_concept_maps", "user_id"),
    ("folder_concept_maps", "user_id"),
    ("device_concept_maps", "user_id"),
    # Media transcripts
    ("audio_transcripts", "user_id"),
    ("transcripts", "user_id"),
    ("video_transcripts", "user_id"),
    ("video_transcriptions", "user_id"),
    # Chat
    ("ChatSessions", "user_id"),
    ("MessagePairs", "user_id"),
    ("chat_history", "user_id"),
    # Projects
    ("projects", "user_id"),
    ("project_backups", "user_id"),
    # Sharing metadata (records ABOUT this user's resources / their shares)
    ("resources", "user_id"),
    ("public_shares", "user_id"),
    ("shared_with_me", "user_id"),
    ("resource_permissions", "user_id"),
    # ── PRIVATE VAULT ──
    # Folder docs first; their _ids feed the vault_shares cascade
    # in the worker's _purge_personal_resources.
    ("folders", "user_id"),
    ("files", "user_id"),
    ("documents", "user_id"),
    ("documents_v2", "user_id"),
    ("document_chunked", "user_id"),
    ("document_chunked_metadata", "user_id"),
    ("chunks_v2", "user_id"),
    ("milvus_chunks", "user_id"),
    ("citra_ai_chunks", "user_id"),
    ("structured_file_metadata", "user_id"),
    ("unstructured_file_metadata", "user_id"),
]


# Legacy alias kept so any code that imported the vault subset still
# resolves. New code should use PRIVATE_PERSONAL_COLLECTIONS.
PRIVATE_VAULT_COLLECTIONS = [
    ("files", "user_id"),
    ("documents", "user_id"),
    ("documents_v2", "user_id"),
    ("document_chunked", "user_id"),
    ("document_chunked_metadata", "user_id"),
    ("chunks_v2", "user_id"),
    ("milvus_chunks", "user_id"),
    ("citra_ai_chunks", "user_id"),
    ("folders", "user_id"),
    ("structured_file_metadata", "user_id"),
    ("unstructured_file_metadata", "user_id"),
]


def _admin_check(request: Request):
    """Only org_admin / super_admin may call these admin endpoints.

    Mirrors the role check used elsewhere — read roles from request.state
    populated by auth_middleware. Returns the caller's email on success;
    raises 403 otherwise.
    """
    user = getattr(request.state, "user", None) or {}
    roles = set(user.get("roles") or [])
    if not (roles & {"org_admin", "super_admin"}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="org_admin or super_admin required",
        )
    return user.get("email") or user.get("user_id") or ""


@router.get("/admin/user-content-summary")
async def admin_user_content_summary(request: Request, email: str) -> Dict[str, Any]:
    """Return per-bucket counts of personal content for one user.

    Used by the admin-delete picker preflight to show the admin what's
    about to be archived / transferred / wiped beyond workflows + apps.

    Auth: org_admin / super_admin only. The caller must speak for the
    same org as the target user (super_admin bypasses).
    """
    _admin_check(request)
    target = (email or "").strip().lower()
    if not target:
        raise HTTPException(status_code=400, detail="email required")

    from citra_mongo import get_async_mongo_client, MONGODB_DATABASE
    db = get_async_mongo_client()[MONGODB_DATABASE]

    summary: Dict[str, Dict[str, Any]] = {}
    grand_total = 0
    for bucket, entries in CONTENT_BUCKETS.items():
        bucket_total = 0
        per_collection: Dict[str, int] = {}
        for coll_name, field in entries:
            try:
                n = await db[coll_name].count_documents({field: target})
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[user-content-summary] {coll_name}: {exc}")
                n = 0
            per_collection[coll_name] = n
            bucket_total += n
        summary[bucket] = {"total": bucket_total, "by_collection": per_collection}
        grand_total += bucket_total

    return {
        "success": True,
        "email": target,
        "grand_total": grand_total,
        "buckets": summary,
    }


class _ApplyRequest(BaseModel):
    email: str
    # Per-bucket policy; missing buckets default to "keep".
    bucket_policies: Dict[str, str] = {}
    # When policy="transfer_to_admin", rewrite user_id to this email.
    # If absent, defaults to the calling admin.
    transfer_target_email: str = ""


_ALLOWED_POLICIES = {"keep", "transfer_to_admin", "delete"}


@router.post("/admin/user-content-apply")
async def admin_user_content_apply(request: Request, body: _ApplyRequest) -> Dict[str, Any]:
    """Apply the admin's per-bucket policy to a user's personal content.

    Per bucket:
      - "keep"               : no-op, returns count only
      - "transfer_to_admin"  : updateMany {field: target} → {$set: {field: new_owner}}
      - "delete"             : deleteMany {field: target}

    Auth: org_admin / super_admin. The caller's email is the default
    transfer target.

    Returns per-bucket {applied_policy, affected_count} for the
    HandoffReport.
    """
    admin_email = _admin_check(request)
    target = (body.email or "").strip().lower()
    if not target:
        raise HTTPException(status_code=400, detail="email required")

    new_owner = (body.transfer_target_email or admin_email or "").strip().lower()

    # Validate policies
    for bucket, policy in (body.bucket_policies or {}).items():
        if bucket not in CONTENT_BUCKETS:
            raise HTTPException(status_code=400, detail=f"unknown bucket '{bucket}'")
        if policy not in _ALLOWED_POLICIES:
            raise HTTPException(
                status_code=400,
                detail=f"invalid policy '{policy}' for bucket '{bucket}' "
                       f"(allowed: {sorted(_ALLOWED_POLICIES)})",
            )
        if policy == "transfer_to_admin" and not new_owner:
            raise HTTPException(
                status_code=400,
                detail="transfer_target_email required when policy=transfer_to_admin",
            )

    from citra_mongo import get_async_mongo_client, MONGODB_DATABASE
    db = get_async_mongo_client()[MONGODB_DATABASE]

    results: Dict[str, Any] = {}
    for bucket, entries in CONTENT_BUCKETS.items():
        policy = (body.bucket_policies or {}).get(bucket, "keep")
        bucket_affected = 0
        per_coll_results: Dict[str, Dict[str, Any]] = {}
        for coll_name, field in entries:
            try:
                coll = db[coll_name]
                if policy == "delete":
                    r = await coll.delete_many({field: target})
                    n = r.deleted_count
                elif policy == "transfer_to_admin":
                    r = await coll.update_many(
                        {field: target}, {"$set": {field: new_owner}}
                    )
                    n = r.modified_count
                else:  # keep
                    n = await coll.count_documents({field: target})
                per_coll_results[coll_name] = {"applied": policy, "affected": n}
                bucket_affected += n
            except Exception as exc:  # noqa: BLE001
                logger.exception(f"[user-content-apply] {coll_name}: {exc}")
                per_coll_results[coll_name] = {
                    "applied": policy, "affected": 0, "error": str(exc),
                }
        results[bucket] = {
            "policy": policy,
            "affected": bucket_affected,
            "by_collection": per_coll_results,
        }

    logger.warning(
        f"🪦 [user-content-apply] admin={admin_email} target={target} "
        f"policies={body.bucket_policies} new_owner={new_owner if new_owner != admin_email else '(self)'}"
    )
    return {
        "success": True,
        "email": target,
        "admin": admin_email,
        "transfer_target": new_owner,
        "buckets": results,
    }


# ── Internal admin S3 purge ─────────────────────────────────────────────────


class _AdminPurgeS3Request(BaseModel):
    email: str


@router.post("/admin/purge-user-s3")
async def admin_purge_user_s3(request: Request, body: _AdminPurgeS3Request) -> Dict[str, Any]:
    """Wipe every S3 object scoped to the user's prefixes.

    Called by Citra-Worker during ``user.delete_applied`` so the user's
    uploads (vault files, page builder images, etc.) don't leak after
    deletion. The prefixes match what user-initiated GDPR delete wipes
    (see :func:`delete_all_user_data`) — kept in sync deliberately.

    Auth: org_admin / super_admin. The worker calls this with the
    deleting admin's JWT, so role-bound.
    """
    _admin_check(request)
    target = (body.email or "").strip().lower()
    if not target:
        raise HTTPException(status_code=400, detail="email required")

    s3_deleted = 0
    errors = []
    try:
        from bucket import _get_client, get_config, get_environment_prefix
        from utils import sanitize_container_name

        s3_bucket, _ = get_config()
        s3 = _get_client()
        env_prefix = get_environment_prefix()
        sanitized_email = sanitize_container_name(target)

        # Same prefixes the user-initiated GDPR purge sweeps.
        prefixes_to_delete = [
            f"{env_prefix}/{sanitized_email}/",
            f"pages/{target}/",
        ]
        per_prefix: Dict[str, int] = {}
        for prefix in prefixes_to_delete:
            try:
                paginator = s3.get_paginator("list_objects_v2")
                pages = paginator.paginate(Bucket=s3_bucket, Prefix=prefix)
                objects_to_delete = []
                for page in pages:
                    for obj in page.get("Contents", []):
                        objects_to_delete.append({"Key": obj["Key"]})
                for i in range(0, len(objects_to_delete), 1000):
                    batch = objects_to_delete[i:i + 1000]
                    s3.delete_objects(Bucket=s3_bucket, Delete={"Objects": batch})
                    s3_deleted += len(batch)
                per_prefix[prefix] = len(objects_to_delete)
                if objects_to_delete:
                    logger.info(
                        "[admin-purge-s3] target=%s prefix='%s' deleted=%d",
                        target, prefix, len(objects_to_delete),
                    )
            except Exception as prefix_err:
                logger.error("[admin-purge-s3] prefix '%s' failed: %s", prefix, prefix_err)
                errors.append(f"{prefix}: {prefix_err}")
        return {
            "success": True,
            "email": target,
            "s3_files_deleted": s3_deleted,
            "per_prefix": per_prefix,
            "errors": errors,
        }
    except Exception as e:
        logger.error("[admin-purge-s3] failed for %s: %s", target, e)
        raise HTTPException(status_code=500, detail=f"S3 cleanup failed: {e}")
