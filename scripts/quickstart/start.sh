#!/usr/bin/env bash
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

cat <<EOF

----------------------------------------------------------------------------
citra-decks is running.

   Web UI          http://localhost:8094
   Backend API     http://localhost:8093  (docs: /docs)
   Collaboration   ws://localhost:1234    (health: /health)
   MinIO console   http://localhost:9003

   Register your first account from the web UI — there is no seeded admin;
   the local auth backend (api/local_auth.py) creates accounts on demand.

   Guide           README.md
----------------------------------------------------------------------------
EOF
