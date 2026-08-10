#!/usr/bin/env bash
# Guided first-run setup:
#   1. .env with fresh secrets
#   2. AI provider — one OpenRouter key for drafting, grounding and vision
#   3. image generation — a Runware key (required; it is what puts imagery
#      on the slides, and the OpenRouter key does not cover it)
#   4. bring the stack up
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
hr; echo "$(b "Step 1/4 — environment file")"
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
# Required, and deliberately Runware only. Without imagery a generated deck is
# a text outline — no cover art, no section visuals — which is the largest
# single difference in how the output looks, and it costs a few cents an
# image, so declining saves nothing worth having.
#
# One backend here, not a menu: Runware is what this product has actually been
# built and tested against. The code supports two others (any OpenAI-compatible
# image endpoint, and self-hosted ComfyUI) and .env documents both, but the
# wizard's job is to produce a configuration that works on the first run rather
# than to enumerate every possibility.
hr; echo "$(b "Step 3/4 — image generation (required)")"
echo "Runware generates the cover art and section imagery on your slides and"
echo "report pages. Without it decks come out plain: text and charts only —"
echo "the biggest single difference in how the output looks. A few cents per"
echo "image, so a full deck costs very little."
echo
echo "This is the one thing the OpenRouter key does not cover, so it needs"
echo "its own. Get one at: $(b "https://runware.ai")"
echo
echo "The model below is a QUICK-START DEFAULT — press Enter to accept it."
echo "Other backends (any OpenAI-compatible image endpoint, or a self-hosted"
echo "ComfyUI) are configurable later in .env; see the IMAGE_GEN_ notes there."
rw="$(ask_secret "Runware API key (input hidden)")"
if [ -z "$rw" ]; then
  echo
  echo "  [FAIL] no key entered. Decks would generate without any imagery," >&2
  echo "         which is not what this product is for. Re-run once you have" >&2
  echo "         a key — or, if you truly want imagery off, set the IMAGE_GEN_" >&2
  echo "         variables yourself in .env and skip this wizard." >&2
  exit 1
fi
# Asked rather than hardcoded so a Runware user can pick their model, but
# defaulted so pressing Enter always yields a working config. The default is
# the AIR id this repo ships and relies on: image_gen_api.py names it
# EDIT_CAPABLE_MODEL because it does generation AND editing, and Runware is the
# only backend whose edit action works — swap it only for something that also
# supports edits, or the composers' edit button starts failing.
rmodel="$(ask "Runware model" "runware:400@1")"
setkv IMAGE_GEN_PROVIDER "runware"
setkv IMAGE_GEN_API_KEY  "$rw"
setkv IMAGE_GEN_MODEL    "${rmodel:-runware:400@1}"
setkv IMAGE_GEN_BASE_URL ""
echo "  [ok] Runware configured (${rmodel:-runware:400@1}) — slides will have imagery"

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
