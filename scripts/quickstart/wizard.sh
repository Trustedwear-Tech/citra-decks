#!/usr/bin/env bash
# Guided first-run setup:
#   1. .env with fresh secrets
#   2. AI provider (required — generation needs a model)
#   3. bring the stack up
#
# Re-runnable: reads and updates the existing .env, so run it again to change
# a key. Prereqs: docker, curl, openssl.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$REPO_ROOT"
ENV_FILE="$REPO_ROOT/.env"

b()  { printf '\033[1m%s\033[0m' "$1"; }
hr() { printf '\n------------------------------------------------------------\n'; }
ask() {
  local q="$1" def="${2:-}" ans
  if [ -n "$def" ]; then printf '%s [%s]: ' "$q" "$def" >&2; else printf '%s: ' "$q" >&2; fi
  read -r ans || true; printf '%s' "${ans:-$def}"
}
ask_secret() { local q="$1" ans; printf '%s: ' "$q" >&2; read -rs ans || true; printf '\n' >&2; printf '%s' "$ans"; }
yes_no() { local q="$1" def="${2:-y}" a; a="$(ask "$q (y/n)" "$def")"; case "$a" in y|Y|yes|YES) return 0;; *) return 1;; esac; }

rand()  { openssl rand -hex "$1" 2>/dev/null || head -c "$((${1}*2))" /dev/urandom | od -An -tx1 | tr -d ' \n'; }
getkv() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- ; }
setkv() {
  local k="$1" v="$2"
  if grep -qE "^$k=" "$ENV_FILE" 2>/dev/null; then
    awk -v k="$k" -v v="$v" 'BEGIN{FS="="} $1==k{print k"="v; next} {print}' "$ENV_FILE" > "$ENV_FILE.tmp" && mv "$ENV_FILE.tmp" "$ENV_FILE"
  else
    printf '%s=%s\n' "$k" "$v" >> "$ENV_FILE"
  fi
}

clear 2>/dev/null || true
echo "$(b "citra-decks — setup wizard")"
echo "Sovereign presentations, visual reports and long-form documents."

# -- 1. .env ------------------------------------------------------------------
hr; echo "$(b "Step 1/3 — environment file")"
if [ -f "$ENV_FILE" ]; then
  echo "Found an existing .env — keeping it (values you set are preserved)."
else
  echo "Generating .env from .env.example with fresh random secrets..."
  cp .env.example "$ENV_FILE"
  MONGO_PW="$(rand 16)"
  setkv MONGODB_PASSWORD "$MONGO_PW"
  setkv MONGODB_CONN_STRING "mongodb://root:${MONGO_PW}@mongodb:27017/?authSource=admin&replicaSet=rs0"
  setkv JWT_SECRET "$(rand 48)"
  setkv CONNECTION_ENCRYPTION_KEY "$(rand 32)"
  echo "  [ok] secrets generated (Mongo password, JWT secret, encryption key)"
fi

# -- 2. AI provider -------------------------------------------------------------
# ONE provider, deliberately. A single OpenRouter key covers reasoning,
# embeddings and vision, so there is one key to paste and one thing that can be
# wrong. Offering four providers previously set only the LLM_* vars — a user who
# picked OpenAI finished the wizard with EMBEDDING_BASE_URL still empty, so the
# composers came up unable to ground anything in their documents, silently.
# Every default below is open-weights and swappable by editing .env.
hr; echo "$(b "Step 2/4 — AI provider (required)")"
echo "The composers call an LLM to draft, an embedding model to ground that"
echo "draft in your documents, and a vision model to read images. One"
echo "OpenRouter key covers all three."
echo
echo "  Get a key: $(b "https://openrouter.ai/keys")"
key="$(ask_secret "Paste your OpenRouter API key (input hidden)")"

if [ -z "$key" ]; then
  echo
  echo "  [FAIL] no key entered. Presentation/printable generation cannot" >&2
  echo "         produce anything without a model. Re-run once you have a key." >&2
  exit 1
fi

base="https://openrouter.ai/api/v1"
model="deepseek/deepseek-v4-pro"
setkv LLM_LARGE_BASE_URL  "$base"; setkv LLM_LARGE_MODEL  "$model"; setkv LLM_LARGE_API_KEY  "$key"
setkv LLM_MEDIUM_BASE_URL "$base"; setkv LLM_MEDIUM_MODEL "$model"; setkv LLM_MEDIUM_API_KEY "$key"
setkv LLM_SMALL_BASE_URL  "$base"; setkv LLM_SMALL_MODEL  "$model"; setkv LLM_SMALL_API_KEY  "$key"
# Slide and report layout stays pinned to GLM-5.1 — it produces the best
# structure of the models tested, and OpenRouter carries it.
setkv PRESENTATION_LLM_MODEL "z-ai/glm-5.1"
setkv PRINTABLE_LLM_MODEL    "z-ai/glm-5.1"
# Grounding. Without these the composers still draft, but from nothing but the
# prompt — the one thing this product exists not to do.
setkv EMBEDDING_BASE_URL  "$base"
setkv EMBEDDING_MODEL     "baai/bge-m3"
setkv EMBEDDING_DIMENSION "768"
setkv EMBEDDING_API_KEY   "$key"
# Vision credentials are wired up even though the critique pass ships OFF
# (CRITIC_VISION_ENABLED=false, set below), so switching it on later is a
# one-line change rather than another trip through the wizard.
setkv VISION_BASE_URL "$base"
setkv VISION_MODEL    "qwen/qwen3-vl-32b-instruct"
setkv VISION_API_KEY  "$key"
echo "  [ok] one key configured for drafting and grounding"
echo "       (vision credentials set too, but the critique pass stays off)"

# -- 3. Image generation ----------------------------------------------------------
# Asked as a real question with a default of YES, not buried as an optional
# extra. Without imagery a generated deck is a text outline: no cover art, no
# section visuals. It is the largest single difference in how the output
# LOOKS, it costs a few cents per image, and a user who skips it will
# reasonably conclude the product produces plain slides. Skipping stays
# possible — it just is not the path of least resistance any more.
hr; echo "$(b "Step 3/4 — image generation (strongly recommended)")"
echo "Runware generates the cover art and section imagery on your slides and"
echo "report pages. It is not served by OpenRouter, so it needs its own key."
echo
echo "  Without it, generation still works — but decks come out plain: no"
echo "  cover art, no visuals, just text and charts. This is the biggest"
echo "  single difference in how the output looks."
echo "  A few cents per image; a full deck costs very little."
echo
echo "  Get a key: $(b "https://runware.ai")"
if yes_no "Add your Runware key now?" "y"; then
  rw="$(ask_secret "Runware API key")"
  if [ -n "$rw" ]; then
    setkv IMAGE_GEN_PROVIDER "runware"
    setkv IMAGE_GEN_API_KEY  "$rw"
    setkv IMAGE_GEN_MODEL    "runware:400@1"
    echo "  [ok] Runware configured — slides will have generated imagery"
  else
    echo "  [!] no key entered — decks will generate WITHOUT imagery."
    echo "      Add IMAGE_GEN_API_KEY to .env later to turn it on."
  fi
else
  echo "  [!] skipped — decks will generate WITHOUT imagery."
  echo "      Add IMAGE_GEN_API_KEY to .env later to turn it on."
fi

# Vision is a different thing from image generation, and it is OFF by default.
# It re-renders each finished slide and sends the image to a vision model to
# detect overlaps and patch layout — real cost on every generation, for a
# problem most decks do not have. Turn it on only after seeing a glitch.
setkv CRITIC_VISION_ENABLED "false"

# -- 4. Bring it up ---------------------------------------------------------------
hr; echo "$(b "Step 4/4 — bring up the stack")"
if yes_no "Run setup now (data stores)?" "y"; then
  "$REPO_ROOT/scripts/quickstart/setup.sh"
fi
if yes_no "Start all services?" "y"; then
  "$REPO_ROOT/scripts/quickstart/start.sh"
fi

hr
echo "$(b "Done.")  Open  http://localhost:8094  and create your first account."
echo "Re-run this wizard any time to change keys:  ./scripts/quickstart/wizard.sh"
