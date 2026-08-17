#!/usr/bin/env bash
# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

# PHASE 2 — START. Brings up citra-decks end to end:
#   1. docker compose up -d  (backend, collaboration server, web shell)
#   2. wait for the backend to answer /health
#
# Run AFTER ./scripts/quickstart/setup.sh. Idempotent.
# Prereqs on host: docker, curl.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"
[ -f .env ] || { echo "No .env — run ./scripts/quickstart/setup.sh first." >&2; exit 1; }

COMPOSE="docker compose -f docker-compose.yml"

getenv() { grep -E "^$1=" .env | head -1 | cut -d= -f2-; }

if [ -z "$(getenv LLM_LARGE_API_KEY)" ]; then
  echo "[FAIL] LLM_LARGE_API_KEY is empty in .env." >&2
  echo "       Presentation and printable generation cannot produce anything" >&2
  echo "       without a model. Get an OpenRouter key at" >&2
  echo "       https://openrouter.ai/keys, set it in .env, then re-run." >&2
  echo "       (Later, point LLM_LARGE_BASE_URL at your own in-house vLLM" >&2
  echo "       endpoint instead — see README.md.)" >&2
  exit 1
fi

# -- 1. Start everything --------------------------------------------------------
echo "-> starting all services (docker compose up -d)"
$COMPOSE up -d --build

# -- 2. Wait for the backend ------------------------------------------------------
echo -n "-> waiting for backend "
BACKEND_OK=false
for _ in $(seq 1 60); do
  if curl -fsS "http://localhost:8093/health" >/dev/null 2>&1; then
    echo " OK"; BACKEND_OK=true; break
  fi
  printf "."; sleep 5
done
if [ "$BACKEND_OK" != true ]; then
  echo " TIMEOUT"
  echo "   backend not healthy at http://localhost:8093/health — check: $COMPOSE logs backend" >&2
  exit 1
fi

# -- 3. Milvus vector-search collection ------------------------------------------
# The backend does not auto-create its Milvus collection; without it, semantic
# retrieval for grounding degrades. The setup script exits non-zero when the
# collection already exists, so parse its output rather than the exit code.
echo "-> ensuring the Milvus vector-search collection"
milvus_out="$($COMPOSE exec -T backend python scripts/setup_milvus_schema.py 2>&1 || true)"
if printf '%s' "$milvus_out" | grep -qiE "Schema setup successful"; then
  $COMPOSE restart backend >/dev/null 2>&1 || true
  echo "   [ok] Milvus collection created"
elif printf '%s' "$milvus_out" | grep -qiE "already exists"; then
  echo "   [ok] Milvus collection already present"
else
  echo "   [!] could not confirm the Milvus collection — retrieval grounding for" >&2
  echo "       generation may be degraded until scripts/setup_milvus_schema.py" >&2
  echo "       runs successfully. Not fatal; generation still works without it." >&2
fi

# -- 4. Compute sandbox image ----------------------------------------------------
# services/code_executor.py spawns a container from this image to run the small
# Python scripts that produce real figures from your spreadsheets — the
# "numbers are computed, not generated" path in ARCHITECTURE.md §1. NOTHING
# built it: the Dockerfile is referenced by no compose file, Makefile or
# script, so on a fresh install the image was simply absent, every compute call
# failed to spawn, and figures silently fell back to whatever the model said —
# exactly the failure that design exists to prevent.
#
# The image name is quick-chat-sandbox because it outlived the Quick Chat
# surface that named it; code_executor.py and sandbox_pool.py both default to
# that string, so renaming it here would break them.
SANDBOX_IMAGE="${QUICK_CHAT_SANDBOX_IMAGE:-quick-chat-sandbox}"
if docker image inspect "$SANDBOX_IMAGE" >/dev/null 2>&1; then
  echo "-> compute sandbox image present"
else
  echo "-> building the compute sandbox image ($SANDBOX_IMAGE) — first run only"
  if docker build -q -t "$SANDBOX_IMAGE" -f Dockerfile.quick-chat-sandbox . >/dev/null 2>&1; then
    echo "   [ok] sandbox built — figures will be computed from your files"
  else
    echo "   [!] sandbox build failed. Generation still works, but figures will" >&2
    echo "       come from the model rather than being computed from your data." >&2
    echo "       Retry: docker build -t $SANDBOX_IMAGE -f Dockerfile.quick-chat-sandbox ." >&2
  fi
fi

# Read the published ports back out of .env so an override actually shows here.
# Hardcoding them meant the banner confidently printed the wrong URL for anyone
# who had changed one — the defaults must match docker-compose.yml.
# `|| true` is required, not decorative: getenv greps .env, this script runs
# under `set -euo pipefail`, and these keys are absent from .env whenever the
# compose defaults are being used — so grep exits 1, the pipeline fails, and
# the script would abort here without ever printing the banner.
WEB_PORT="$(getenv WEB_HOST_PORT || true)";          WEB_PORT="${WEB_PORT:-8094}"
BACKEND_PORT="$(getenv BACKEND_HOST_PORT || true)";  BACKEND_PORT="${BACKEND_PORT:-8093}"
CONSOLE_PORT="$(getenv MINIO_CONSOLE_PORT || true)"; CONSOLE_PORT="${CONSOLE_PORT:-9023}"

cat <<EOF

----------------------------------------------------------------------------
citra-decks is running.

   Web UI          http://localhost:${WEB_PORT}
   Backend API     http://localhost:${BACKEND_PORT}  (docs: /docs)
   Collaboration   ws://localhost:1234    (health: /health)
   MinIO console   http://localhost:${CONSOLE_PORT}

   Sign in: nothing is seeded — register your first account from the web
   UI's sign-up screen (any email + password; accounts are created on
   demand by api/local_auth.py, stored in this stack's own Mongo).

   All accounts are equal: no admin role, no orgs — each account is its
   own private workspace. Registration is open to anyone who can reach
   this port, and password reset is NOT wired up (the forgot-password
   endpoint is a stub) — run this on a network you trust, and keep your
   password safe.

   Guide           README.md
----------------------------------------------------------------------------
EOF
