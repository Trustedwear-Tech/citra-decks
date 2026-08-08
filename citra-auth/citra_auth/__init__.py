"""citra-auth — shared JWT auth middleware + helpers."""

from .middleware import (
    JWTAuthMiddleware,
    get_current_user,
    is_authenticated,
    get_user_email,
    get_user_id,
    get_authenticated_user_id,
    extract_user_identifier,
    get_secure_user_id,
    mint_workflow_system_token,
    mint_workflow_org_token,
    mint_system_workflow_token,
    mint_semantic_read_token,
    # Exported for tests that need to temporarily flip the DISABLE_AUTH
    # bypass on/off and re-evaluate. Production code should NOT use this.
    _is_auth_disabled,
)
from .revocation import (
    register_revocation_checker,
    has_revocation_checker,
    is_token_revoked,
)
from .constants import Roles, OwnerType, EntityType

__all__ = [
    "JWTAuthMiddleware",
    "get_current_user",
    "is_authenticated",
    "get_user_email",
    "get_user_id",
    "get_authenticated_user_id",
    "extract_user_identifier",
    "get_secure_user_id",
    "mint_workflow_system_token",
    "mint_workflow_org_token",
    "mint_system_workflow_token",
    "mint_semantic_read_token",
    "_is_auth_disabled",
    # ── Token revocation seam ──
    "register_revocation_checker",
    "has_revocation_checker",
    "is_token_revoked",
    # ── Shared identity vocabulary (role / owner_type / entity_type names) ──
    "Roles",
    "OwnerType",
    "EntityType",
]
