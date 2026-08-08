"""citra-queue — Redis-backed job queue, one source of truth for
producer + consumer across all Citra services.
"""
from .queue import (
    DEFAULT_QUEUE,
    DEFAULT_MAX_RETRIES,
    RESULT_TTL_SECONDS,
    GROUP,
    Job,
    JobPermanentFailure,
    enqueue,
    get_status,
    consume_one,
    claim_stale,
    queue_depth,
    dlq_depth,
    default_consumer_name,
    mark_running,
    mark_done,
    mark_failed,
)

__all__ = [
    "DEFAULT_QUEUE",
    "DEFAULT_MAX_RETRIES",
    "RESULT_TTL_SECONDS",
    "GROUP",
    "Job",
    "JobPermanentFailure",
    "enqueue",
    "get_status",
    "consume_one",
    "claim_stale",
    "queue_depth",
    "dlq_depth",
    "default_consumer_name",
    "mark_running",
    "mark_done",
    "mark_failed",
]
