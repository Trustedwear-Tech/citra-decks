"""
Resource taxonomy — single source of truth across the platform.

MANAGED resources are admin-visible: dept_admin / org_admin can list,
transfer, and delete them. On user deletion the admin chooses
keep / transfer-to-SA / transfer-to-dept / delete via the per-resource
picker.

PERSONAL resources are admin-invisible. On user deletion they are
hard-cascade-deleted (no picker, just a count + confirmation). Sharing
is per-resource (team_share + public_share) via the centralised
authorization_service.

KEEP THESE THREE LISTS IN LOCKSTEP:
  - Citra-User-Service/src/config/resourceTaxonomy.js  (JS)
  - Citra-Service/config/resource_taxonomy.py          (this file)
  - Citra-UI/services/resourceTaxonomy.js              (frontend mirror)
"""
from __future__ import annotations

from typing import FrozenSet


MANAGED_RESOURCES: FrozenSet[str] = frozenset({
    "workflow",
    "smart_app",
})

PERSONAL_RESOURCES: FrozenSet[str] = frozenset({
    "presentation",
    "report",      # backed by composer_reports collection
    "printable",
    "diagram",     # mindmaps share this collection
    "note",        # backed by Notes collection (capital N)
    "page",        # page_blocks + page_databases cascade with this
    "vault",       # backed by folders collection
    "project",
})

ALL_RESOURCES: FrozenSet[str] = MANAGED_RESOURCES | PERSONAL_RESOURCES


def is_managed(resource_type: str) -> bool:
    return resource_type in MANAGED_RESOURCES


def is_personal(resource_type: str) -> bool:
    return resource_type in PERSONAL_RESOURCES
