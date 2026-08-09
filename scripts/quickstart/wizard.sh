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
hr; echo "$(b "Step 2/3 — AI provider (required)")"
echo "Presentation and printable generation stay pinned to GLM-5.1 by default"
echo "(the model that produces the best slide/report layouts) — but any"
echo "OpenAI-compatible endpoint works. Pick your provider:"
echo "  1) OpenRouter    (one key, many models — GLM-5.1 included, easiest to evaluate)"
echo "  2) OpenAI"
echo "  3) DeepSeek"
echo "  4) Self-hosted   (vLLM / TGI / Ollama — your own endpoint)"
choice="$(ask "Choose 1-4" "1")"
case "$choice" in
  1) base="https://openrouter.ai/api/v1"; model="deepseek/deepseek-v4-pro"; pmodel="z-ai/glm-5.1"; url="https://openrouter.ai/keys" ;;
  2) base="https://api.openai.com/v1";    model="gpt-4o";                   pmodel="gpt-4o";       url="https://platform.openai.com/api-keys" ;;
  3) base="https://api.deepseek.com/v1";  model="deepseek-chat";            pmodel="deepseek-chat"; url="https://platform.deepseek.com" ;;
  4) base="$(ask "LLM base URL" "http://host.docker.internal:8000/v1")"; model="$(ask "Model name" "Qwen/Qwen3-32B-Instruct")"; pmodel="$model"; url="" ;;
  *) echo "Unrecognised choice '$choice'." >&2; exit 1 ;;
esac
[ -n "$url" ] && echo "Get a key: $(b "$url")"
key="$(ask_secret "Paste your API key (input hidden)")"

if [ -z "$key" ] && [ "$choice" != "4" ]; then
  echo
  echo "  [FAIL] no key entered. Presentation/printable generation cannot" >&2
  echo "         produce anything without a model. Re-run once you have a key." >&2
  exit 1
fi

setkv LLM_LARGE_BASE_URL "$base"; setkv LLM_LARGE_MODEL "$model"
setkv LLM_MEDIUM_BASE_URL "$base"; setkv LLM_MEDIUM_MODEL "$model"
setkv LLM_SMALL_BASE_URL "$base"; setkv LLM_SMALL_MODEL "$model"
[ -n "$key" ] && { setkv LLM_LARGE_API_KEY "$key"; setkv LLM_MEDIUM_API_KEY "$key"; setkv LLM_SMALL_API_KEY "$key"; } \
  || { setkv LLM_LARGE_API_KEY "not-required-for-self-hosted"; setkv LLM_MEDIUM_API_KEY "not-required-for-self-hosted"; setkv LLM_SMALL_API_KEY "not-required-for-self-hosted"; }
if [ "$choice" = "1" ]; then
  # Only OpenRouter is known to carry GLM-5.1 — every other provider falls
  # back to its own general model rather than silently pointing PRESENTATION_/
  # PRINTABLE_LLM_MODEL at a slug that provider doesn't serve.
  setkv PRESENTATION_LLM_MODEL "$pmodel"
  setkv PRINTABLE_LLM_MODEL "$pmodel"
else
  setkv PRESENTATION_LLM_MODEL "$model"
  setkv PRINTABLE_LLM_MODEL "$model"
fi
echo "  [ok] provider + model saved"

# -- 3. Bring it up ---------------------------------------------------------------
hr; echo "$(b "Step 3/3 — bring up the stack")"
if yes_no "Run setup now (data stores)?" "y"; then
  "$REPO_ROOT/scripts/quickstart/setup.sh"
fi
if yes_no "Start all services?" "y"; then
  "$REPO_ROOT/scripts/quickstart/start.sh"
fi

hr
echo "$(b "Done.")  Open  http://localhost:8094  and create your first account."
echo "Re-run this wizard any time to change keys:  ./scripts/quickstart/wizard.sh"
