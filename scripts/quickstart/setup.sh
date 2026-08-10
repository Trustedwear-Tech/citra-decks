#!/usr/bin/env bash
# PHASE 1 — SETUP. Prepares the local environment so citra-decks can start:
#   1. generate .env from .env.example with fresh random secrets
#   2. bring up the data stores only (Mongo, Redis, Milvus, MinIO)
#   3. create the MinIO bucket
#
# Idempotent — safe to re-run. After this, run: ./scripts/quickstart/start.sh
# Prereqs on host: docker, curl, openssl (optional).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"
ENV_FILE="$REPO_ROOT/.env"
COMPOSE="docker compose -f docker-compose.yml"

rand() { openssl rand -hex "$1" 2>/dev/null || head -c "$((${1}*2))" /dev/urandom | od -An -tx1 | tr -d ' \n'; }
setkv() { # key value file
  local k="$1" v="$2" f="$3"
  if grep -qE "^$k=" "$f"; then
    awk -v k="$k" -v v="$v" 'BEGIN{FS="="} $1==k{print k"="v; next} {print}' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
  else
    printf '\n%s=%s\n' "$k" "$v" >> "$f"
  fi
}

# -- 1. Generate .env with fresh secrets --------------------------------------
if [ -f "$ENV_FILE" ]; then
  echo "-> .env already exists — keeping it (delete it to regenerate)."
else
  echo "-> generating .env from .env.example with fresh secrets"
  cp .env.example "$ENV_FILE"
  MONGO_PW="$(rand 16)"
  setkv MONGODB_PASSWORD "$MONGO_PW" "$ENV_FILE"
  setkv MONGODB_CONN_STRING "mongodb://root:${MONGO_PW}@mongodb:27017/?authSource=admin&replicaSet=rs0" "$ENV_FILE"
  setkv JWT_SECRET "$(rand 48)" "$ENV_FILE"
  setkv CONNECTION_ENCRYPTION_KEY "$(rand 32)" "$ENV_FILE"
  echo "   [ok] secrets generated (Mongo password, JWT secret, encryption key)"
  echo "   [!]  set an LLM_LARGE_API_KEY in .env before start.sh — presentation/"
  echo "        printable generation need it (GLM-5.1 via OpenRouter by default)"
fi

# -- 2. Bring up the data stores only -----------------------------------------
echo "-> starting data stores (Mongo, Redis, Milvus, MinIO)"
$COMPOSE up -d mongodb mongodb-init-rs redis milvus-etcd milvus-minio milvus minio

# -- 3. Wait for Mongo's replica set to initiate -------------------------------
echo "-> waiting for Mongo (replica set self-initiates)"
MONGO_PW="$(grep -E '^MONGODB_PASSWORD=' "$ENV_FILE" | cut -d= -f2-)"
MONGO_USER="$(grep -E '^MONGODB_USER=' "$ENV_FILE" | cut -d= -f2-)"; MONGO_USER="${MONGO_USER:-root}"
MONGO_OK=false
for _ in $(seq 1 60); do
  # Capture rather than discard: an auth failure is a DIFFERENT problem from a
  # replica set that has not formed yet, and only the output distinguishes them.
  out="$($COMPOSE exec -T mongodb mongosh --quiet -u "$MONGO_USER" -p "$MONGO_PW" \
          --authenticationDatabase admin --eval "rs.status().ok" 2>&1 || true)"
  case "$out" in
    *1*) case "$out" in *Error*) ;; *) echo "   [ok] Mongo replica set ready"; MONGO_OK=true; break ;; esac ;;
  esac
  case "$out" in
    *"Authentication failed"*)
      # MONGO_INITDB_ROOT_PASSWORD is honoured ONLY when mongod initialises an
      # EMPTY data directory. A mongodb_data volume left behind by a previous
      # install therefore keeps its ORIGINAL root password, and the fresh one
      # this script just generated into .env is silently ignored. Waiting the
      # full 180s and blaming the replica set sends you to the wrong place --
      # the replica set is fine; the credentials are not.
      echo "   [FAIL] Mongo rejected the password in .env." >&2
      echo "          A data volume from an earlier install is still present, and" >&2
      echo "          it keeps the root password it was FIRST created with -- the" >&2
      echo "          value generated into .env just now is ignored." >&2
      echo "          Either wipe it and start clean:" >&2
      echo "              $COMPOSE down -v" >&2
      echo "          or set MONGODB_PASSWORD in .env back to the original value." >&2
      exit 1 ;;
  esac
  sleep 3
done
if [ "$MONGO_OK" != true ]; then
  echo "   [FAIL] Mongo replica set did not come up within 180s." >&2
  echo "          Check: $COMPOSE logs mongodb mongodb-init-rs" >&2
  exit 1
fi

# -- 4. Create the MinIO bucket -------------------------------------------------
BUCKET_NAME="$(grep -E '^BUCKET_NAME=' "$ENV_FILE" | cut -d= -f2-)"; BUCKET_NAME="${BUCKET_NAME:-citra-documents}"
BUCKET_ACCESS_KEY="$(grep -E '^BUCKET_ACCESS_KEY=' "$ENV_FILE" | cut -d= -f2-)"; BUCKET_ACCESS_KEY="${BUCKET_ACCESS_KEY:-minioadmin}"
BUCKET_SECRET_KEY="$(grep -E '^BUCKET_SECRET_KEY=' "$ENV_FILE" | cut -d= -f2-)"; BUCKET_SECRET_KEY="${BUCKET_SECRET_KEY:-minioadmin}"
echo "-> creating MinIO bucket '$BUCKET_NAME'"
if ! docker run --rm --network citra-decks-network --entrypoint sh minio/mc:latest -c \
  "mc alias set local http://citra-decks-minio:9000 $BUCKET_ACCESS_KEY $BUCKET_SECRET_KEY >/dev/null 2>&1 && \
   mc mb -p local/$BUCKET_NAME >/dev/null 2>&1"; then
  echo "   [FAIL] could not create the MinIO bucket '$BUCKET_NAME'." >&2
  echo "          Every save that stores an image/thumbnail will fail until it" >&2
  echo "          exists. Create it in the MinIO console at http://localhost:${MINIO_CONSOLE_PORT:-9023}" >&2
  echo "          ($BUCKET_ACCESS_KEY/$BUCKET_SECRET_KEY), then re-run this script." >&2
  exit 1
fi
echo "   [ok] bucket '$BUCKET_NAME' present"

cat <<EOF

----------------------------------------------------------------------------
Setup complete. Data stores are up and initialised.

   Next:  set LLM_LARGE_API_KEY in .env, then run  ./scripts/quickstart/start.sh
          (or just: make start)
----------------------------------------------------------------------------
EOF
