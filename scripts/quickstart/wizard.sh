#!/usr/bin/env bash
# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

# Guided first-run setup:
#   1. .env with fresh secrets
#   2. AI provider — one OpenRouter key for drafting, grounding and vision
#   3. image generation — a Runware key (required; it is what puts imagery
#      on the slides, and the OpenRouter key does not cover it)
#   4. bring the stack up
#
#   wizard.sh            install, or resume/repair (keeps .env and your data)
#   wizard.sh --fresh    full cleanup — volumes deleted — then set up from nothing
#   wizard.sh --help     what each mode does
#
# Re-runnable: reads and updates the existing .env, so run it again to change
# a key — Enter keeps any key that is already set. Prereqs: docker, curl,
# openssl.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$REPO_ROOT"
ENV_FILE="$REPO_ROOT/.env"

usage() {
  cat <<'EOF'
citra-decks — guided setup wizard.

Usage:  scripts/quickstart/wizard.sh [--fresh] [-h|--help]

Without options — install, or RESUME:
  Idempotent, safe to re-run any time (after a reboot, to change a key, or
  after a failed first attempt). An existing .env is kept — models and
  settings you tuned by hand are preserved, and pressing Enter at a key
  prompt keeps the key already stored. Containers are started or updated
  in place; your decks, reports, uploads and accounts survive.

--fresh — full cleanup, then set up from nothing:
  Stops the stack and DELETES its volumes — every deck, report, upload
  and account in this install. .env is moved aside to .env.bak.<timestamp>
  (never deleted), then the normal setup runs, asking everything again.
  Asks for confirmation before touching anything.

-h, --help — this text.
EOF
}

FRESH=0
for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    --fresh)   FRESH=1 ;;
    *) echo "unknown option: $arg" >&2; echo "" >&2; usage >&2; exit 2 ;;
  esac
done

# Before the FIRST question. The wizard asks for an OpenRouter key and a
# Runware key before it reaches setup.sh, so a host that cannot run the stack
# used to discover that only after the whole interview was over.
. "$REPO_ROOT/scripts/quickstart/preflight.sh"
preflight || exit 1

b()  { printf '\033[1m%s\033[0m' "$1"; }
hr() { printf '\n------------------------------------------------------------\n'; }
ask() {
  local q="$1" def="${2:-}" ans
  if [ -n "$def" ]; then printf '%s [%s]: ' "$q" "$def" >&2; else printf '%s: ' "$q" >&2; fi
  read -r ans || true; printf '%s' "${ans:-$def}"
}
ask_secret() { local q="$1" ans; printf '%s: ' "$q" >&2; read -rs ans || true; printf '\n' >&2; printf '%s' "$ans"; }
yes_no() { local q="$1" def="${2:-y}" a; a="$(ask "$q (y/n)" "$def")"; case "$a" in y|Y|yes|YES) return 0;; *) return 1;; esac; }
# One '*' per character. Shown after every hidden entry so the user can tell a
# paste landed — and, via the length, that it landed exactly once.
mask() { printf '%*s' "${#1}" '' | tr ' ' '*'; }

# --- Checkpoints -------------------------------------------------------------
# Every completed step is appended to .wizard-state.log (gitignored), and a
# failing run records the step it died in — so the next run can say exactly
# where the last one got to. The log is a RECORD, not an authority: the
# progress report re-verifies every step against .env and Docker, because a
# log that outlives a manual `docker compose down -v` would otherwise lie.
STATE_FILE="$REPO_ROOT/.wizard-state.log"
CURRENT_STEP="preflight"
ckpt() { printf '%s  done: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "$STATE_FILE"; }
trap 'rc=$?; if [ "$rc" -ne 0 ]; then
        word="FAILED"; case "$rc" in 130|143) word="INTERRUPTED";; esac
        printf "%s  %s during: %s (exit %s)\n" "$(date '\''+%Y-%m-%d %H:%M:%S'\'')" "$word" "$CURRENT_STEP" "$rc" >> "$STATE_FILE"
        echo "" >&2
        echo "  [!!] $word during: $CURRENT_STEP. Completed steps are kept —" >&2
        echo "       just re-run the wizard; it resumes from here." >&2
      fi' EXIT
# Ctrl-C / kill: without these, bash skips the EXIT trap on a fatal signal
# and the interruption would never reach the state log.
trap 'exit 130' INT
trap 'exit 143' TERM

progress_report() {
  local s_env="pending" s_or="pending" s_rw="pending" s_ds="pending" s_sv="pending" s_acc
  [ -f "$ENV_FILE" ] && s_env="done   "
  [ -n "$(getkv LLM_LARGE_API_KEY)" ]  && s_or="done   "
  [ -n "$(getkv IMAGE_GEN_API_KEY)" ]  && s_rw="done   "
  docker compose ps -q mongodb 2>/dev/null | grep -q . && s_ds="running"
  docker compose ps -q backend 2>/dev/null | grep -q . && s_sv="running"
  if [ -n "$(getkv ADMIN_EMAIL)" ] && [ -n "$(getkv ADMIN_PASSWORD)" ]; then
    s_acc="seed-on-boot"
  else
    s_acc="registration"
  fi
  echo ""
  echo "Progress — verified against .env and Docker, not just the log:"
  echo "  [${s_env}] .env with generated secrets"
  echo "  [${s_or}] OpenRouter key"
  echo "  [${s_rw}] Runware key"
  echo "  [${s_acc}] your account mode (both are fine — see --help)"
  echo "  [${s_ds}] data stores (mongo, redis, milvus, minio)"
  echo "  [${s_sv}] services (backend, collaboration, web)"
  if [ -f "$STATE_FILE" ]; then
    echo "  log: .wizard-state.log — last entry:"
    tail -1 "$STATE_FILE" | sed 's/^/    /'
    case "$(tail -1 "$STATE_FILE")" in
      *FAILED*|*INTERRUPTED*) echo "  Resuming from that step now." ;;
    esac
  fi
  echo "'pending' runs now; 'done' is kept — Enter keeps stored keys."
}

rand()  { openssl rand -hex "$1" 2>/dev/null || head -c "$((${1}*2))" /dev/urandom | od -An -tx1 | tr -d ' \n'; }
getkv() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true; }
# Quick-start DEFAULTS, as distinct from credentials. Written only when the key
# is missing or empty, so re-running the wizard to update a key never reverts a
# model you tuned by hand. Step 1 promises your values are preserved; before
# this, model names were rewritten anyway, which silently moved LLM_SMALL_MODEL
# and LLM_MEDIUM_MODEL off a cheap tier onto the expensive one and dropped
# OpenRouter ':nitro' routing suffixes — on the highest-volume tier, unasked.
setkv_default() {
  [ -n "$(getkv "$1")" ] && return 0
  setkv "$1" "$2"
}
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

# -- 0. --fresh: cleanup before anything else --------------------------------------
if [ "$FRESH" = 1 ]; then
  hr; echo "$(b "Fresh setup — full cleanup first")"
  echo "This STOPS the stack and DELETES its volumes: every deck, report,"
  echo "upload and account in this install is gone for good."
  echo ".env is moved aside to .env.bak.<timestamp>, not deleted."
  if ! yes_no "Continue?" "n"; then
    # A declined confirmation is a decision, not a failure — disarm the
    # failure trap so the state log does not record it as one.
    trap - EXIT
    echo "Aborted — nothing was touched."
    exit 1
  fi
  CURRENT_STEP="fresh cleanup (down -v)"
  docker compose down -v --remove-orphans
  echo "  [ok] stack stopped, volumes removed"
  if [ -f "$ENV_FILE" ]; then
    bak="$ENV_FILE.bak.$(date +%Y%m%d-%H%M%S)"
    mv "$ENV_FILE" "$bak"
    echo "  [ok] old .env moved to ${bak##*/} (restore it with: mv ${bak##*/} .env)"
  fi
  # The old log describes the install that was just deleted; archive it with
  # the .env so the new log starts at zero and cannot claim finished steps.
  [ -f "$STATE_FILE" ] && mv "$STATE_FILE" "$STATE_FILE.bak.$(date +%Y%m%d-%H%M%S)"
  ckpt "fresh cleanup — volumes deleted, previous .env and state log archived"
fi

progress_report

# -- 1. .env ------------------------------------------------------------------
hr; echo "$(b "Step 1/4 — environment file")"
CURRENT_STEP="environment file"
if [ -f "$ENV_FILE" ]; then
  echo "Found an existing .env — keeping it. The keys you enter below are"
  echo "updated; models and settings you tuned by hand are left as they are."
else
  echo "Generating .env from .env.example with fresh random secrets..."
  cp .env.example "$ENV_FILE"
  MONGO_PW="$(rand 16)"
  setkv MONGODB_PASSWORD "$MONGO_PW"
  setkv MONGODB_CONN_STRING "mongodb://root:${MONGO_PW}@mongodb:27017/?authSource=admin&replicaSet=rs0"
  setkv JWT_SECRET "$(rand 48)"
  setkv CONNECTION_ENCRYPTION_KEY "$(rand 32)"
  echo "  [ok] secrets generated (Mongo password, JWT secret, encryption key)"
  ckpt ".env created with fresh secrets"
fi

# -- 2. AI provider -------------------------------------------------------------
# ONE provider, deliberately. A single OpenRouter key covers reasoning,
# embeddings and vision, so there is one key to paste and one thing that can be
# wrong. Offering four providers previously set only the LLM_* vars — a user who
# picked OpenAI finished the wizard with EMBEDDING_BASE_URL still empty, so the
# composers came up unable to ground anything in their documents, silently.
# Every default below is open-weights and swappable by editing .env.
hr; echo "$(b "Step 2/4 — AI provider (required)")"
CURRENT_STEP="AI provider (OpenRouter key)"
echo "The composers call an LLM to draft, an embedding model to ground that"
echo "draft in your documents, and a vision model to read images. One"
echo "OpenRouter key covers all three."
echo
echo "  Get a key: $(b "https://openrouter.ai/keys")"
# Resume-friendly: "re-run any time to change a key" must not demand keys that
# are already stored. Enter keeps the stored one; the FAIL applies only when
# there is nothing to keep.
cur_or_key="$(getkv LLM_LARGE_API_KEY)"
if [ -n "$cur_or_key" ]; then
  echo "  Stored key: $(mask "$cur_or_key")  (${#cur_or_key} characters)"
  key="$(ask_secret "Paste a NEW OpenRouter key (input hidden; Enter keeps the stored one)")"
  [ -z "$key" ] && echo "  [ok] keeping the stored OpenRouter key"
else
  key="$(ask_secret "Paste your OpenRouter API key (input hidden)")"
  if [ -z "$key" ]; then
    echo
    echo "  [FAIL] no key entered. Presentation/printable generation cannot" >&2
    echo "         produce anything without a model. Re-run once you have a key." >&2
    exit 1
  fi
fi
[ -n "$key" ] && echo "  [ok] key captured: $(mask "$key")  (${#key} characters)"

base="https://openrouter.ai/api/v1"
# Large carries the reasoning work (main chat, code execution, SQL, workflow
# code-gen); small and medium only do cheap classification-style calls
# (transcript cleanup, intent parsing, titles, diagrams), so they run the
# cheaper flash model. Matches .env.example.
large_model="deepseek/deepseek-v4-pro:nitro"
fast_model="deepseek/deepseek-v4-flash:nitro"
# A key is only valid against the endpoint it was issued for, so base URL and
# key are rewritten together whenever a key is entered — and NOT when the
# stored key is kept, which must not overwrite endpoints you pointed elsewhere
# by hand. The MODEL on each tier is a starting point, not a credential —
# setkv_default leaves yours alone (and, on the keep path, only fills gaps).
if [ -n "$key" ]; then
  setkv LLM_LARGE_BASE_URL  "$base"; setkv LLM_LARGE_API_KEY  "$key"
  setkv LLM_MEDIUM_BASE_URL "$base"; setkv LLM_MEDIUM_API_KEY "$key"
  setkv LLM_SMALL_BASE_URL  "$base"; setkv LLM_SMALL_API_KEY  "$key"
fi
setkv_default LLM_LARGE_MODEL  "$large_model"
setkv_default LLM_MEDIUM_MODEL "$fast_model"
setkv_default LLM_SMALL_MODEL  "$fast_model"
# Slide and report layout starts pinned to GLM-5.1 — it produces the best
# structure of the models tested, and OpenRouter carries it.
setkv_default PRESENTATION_LLM_MODEL "z-ai/glm-5.1:nitro"
setkv_default PRINTABLE_LLM_MODEL    "z-ai/glm-5.1:nitro"
# Grounding. Without these the composers still draft, but from nothing but the
# prompt — the one thing this product exists not to do.
# Model and dimension must agree or the Milvus collection is built at the wrong
# width, so both are defaults: swap the model in .env and your dimension is
# still there next time you re-run this to change a key.
if [ -n "$key" ]; then
  setkv EMBEDDING_BASE_URL "$base"
  setkv EMBEDDING_API_KEY  "$key"
  # Vision credentials are wired up even though the critique pass ships OFF
  # (CRITIC_VISION_ENABLED=false, set below), so switching it on later is a
  # one-line change rather than another trip through the wizard.
  setkv VISION_BASE_URL "$base"
  setkv VISION_API_KEY  "$key"
fi
setkv_default EMBEDDING_MODEL     "baai/bge-m3"
setkv_default EMBEDDING_DIMENSION "768"
setkv_default VISION_MODEL    "qwen/qwen3-vl-32b-instruct"
echo "  [ok] one key configured for drafting and grounding"
echo "       (vision credentials set too, but the critique pass stays off)"
[ -n "$key" ] && ckpt "OpenRouter key configured"

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
CURRENT_STEP="image generation (Runware key)"
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
cur_rw="$(getkv IMAGE_GEN_API_KEY)"
if [ -n "$cur_rw" ]; then
  echo "Stored key: $(mask "$cur_rw")  (${#cur_rw} characters)"
  rw="$(ask_secret "Runware API key (input hidden; Enter keeps the stored one)")"
  [ -z "$rw" ] && echo "  [ok] keeping the stored Runware key"
else
  rw="$(ask_secret "Runware API key (input hidden)")"
  if [ -z "$rw" ]; then
    echo
    echo "  [FAIL] no key entered. Decks would generate without any imagery," >&2
    echo "         which is not what this product is for. Re-run once you have" >&2
    echo "         a key — or, if you truly want imagery off, set the IMAGE_GEN_" >&2
    echo "         variables yourself in .env and skip this wizard." >&2
    exit 1
  fi
fi
[ -n "$rw" ] && echo "  [ok] key captured: $(mask "$rw")  (${#rw} characters)"
# Asked rather than hardcoded so a Runware user can pick their model, but
# defaulted so pressing Enter always yields a working config. The default is
# the AIR id this repo ships and relies on: image_gen_api.py names it
# EDIT_CAPABLE_MODEL because it does generation AND editing, and Runware is the
# only backend whose edit action works — swap it only for something that also
# supports edits, or the composers' edit button starts failing.
# On a re-run the offered default is whatever you are already using, so pressing
# Enter keeps it. Offering the shipped id here would revert a deliberate choice
# to the very keystroke that means "no change".
rmodel_cur="$(getkv IMAGE_GEN_MODEL)"
rmodel="$(ask "Runware model" "${rmodel_cur:-runware:400@1}")"
# Provider and key are rewritten only when a NEW key was entered — keeping the
# stored key must not clobber a provider you switched by hand. The model
# answer is applied either way: changing it is a legitimate reason to re-run.
if [ -n "$rw" ]; then
  setkv IMAGE_GEN_PROVIDER "runware"
  setkv IMAGE_GEN_API_KEY  "$rw"
fi
setkv_default IMAGE_GEN_PROVIDER "runware"
setkv IMAGE_GEN_MODEL    "${rmodel:-runware:400@1}"
# Read ONLY by the openai-compatible provider (image_gen_providers.py); the
# Runware provider ignores it. Cleared so a stale endpoint from a previous
# provider cannot come back into play if IMAGE_GEN_PROVIDER is ever switched
# back, and so the file stops implying that editing this URL redirects Runware
# traffic — it does not. Announced, because it is the one value here that is
# deliberately discarded rather than preserved.
if [ -n "$rw" ]; then
  if [ -n "$(getkv IMAGE_GEN_BASE_URL)" ]; then
    echo "  [note] cleared IMAGE_GEN_BASE_URL — Runware does not read it"
  fi
  setkv IMAGE_GEN_BASE_URL ""
fi
echo "  [ok] Runware configured (${rmodel:-runware:400@1}) — slides will have imagery"
[ -n "$rw" ] && ckpt "Runware key configured"

# Vision is a different thing from image generation, and it is OFF by default.
# It re-renders each finished slide and sends the image to a vision model to
# detect overlaps and patch layout — real cost on every generation, for a
# problem most decks do not have. Turn it on only after seeing a glitch.
# A default, not a setting: if you turned the critique pass ON, coming back here
# to update a key must not turn it off again behind you.
setkv_default CRITIC_VISION_ENABLED "false"

# -- Your account (optional seed; no defaults exist) -------------------------------
# A default credential is a credential every install shares, so there is none.
# Enter your own here to have the backend create the account at startup, or
# leave blank and register from the web UI's sign-up screen.
CURRENT_STEP="your account (optional seed)"
if [ -z "$(getkv ADMIN_EMAIL)" ] || [ -z "$(getkv ADMIN_PASSWORD)" ]; then
  hr; echo "$(b "Your account")"
  echo "No default credentials exist. Enter an email + password to have your"
  echo "account created at backend startup — or leave blank to register from"
  echo "the web UI's sign-up screen instead."
  printf 'Email (blank = register in the UI): '
  read -r acc_email || acc_email=""
  if [ -n "$acc_email" ]; then
    acc_pw=""
    while [ -z "$acc_pw" ]; do
      # -s: nothing echoes while typing or pasting; the masked line after is
      # how you verify a paste landed, and landed exactly once.
      printf 'Password (min 8 characters; input hidden): '
      read -rs acc_pw || { acc_pw=""; echo ""; break; }
      echo ""
      if [ "${#acc_pw}" -lt 8 ]; then
        echo "  [!!] too short — 8 characters minimum (got ${#acc_pw})"
        acc_pw=""
      fi
    done
    if [ -n "$acc_pw" ]; then
      setkv ADMIN_EMAIL "$acc_email"
      setkv ADMIN_PASSWORD "$acc_pw"
      echo "  [ok] password captured: $(mask "$acc_pw")  (${#acc_pw} characters)"
      echo "  [ok] will seed ${acc_email} at backend startup"
      ckpt "account configured for seeding (${acc_email})"
    fi
  fi
fi

# -- 4. Bring it up ---------------------------------------------------------------
hr; echo "$(b "Step 4/4 — bring up the stack")"
if yes_no "Run setup now (data stores)?" "y"; then
  CURRENT_STEP="data stores (setup.sh)"
  "$REPO_ROOT/scripts/quickstart/setup.sh"
  ckpt "data stores up (setup.sh)"
fi
if yes_no "Start all services?" "y"; then
  CURRENT_STEP="services (start.sh)"
  "$REPO_ROOT/scripts/quickstart/start.sh"
  ckpt "services up (start.sh)"
fi
CURRENT_STEP="done"

hr
wiz_admin_email="$(getkv ADMIN_EMAIL)"
wiz_admin_pw="$(getkv ADMIN_PASSWORD)"
echo "$(b "Done.")  Open  http://localhost:8094"
echo ""
if [ -n "$wiz_admin_email" ] && [ -n "$wiz_admin_pw" ]; then
  echo "Sign in:  ${wiz_admin_email}  /  $(mask "$wiz_admin_pw") (${#wiz_admin_pw} characters)"
  echo "          (your ADMIN_EMAIL / ADMIN_PASSWORD from .env, seeded at"
  echo "          backend startup — the password is the one you chose and is"
  echo "          never printed; read it with: grep ^ADMIN_ .env. Restarting"
  echo "          the backend resets it to the .env value — its recovery path)"
else
  echo "Sign in:  register your account on the login screen's sign-up form —"
  echo "          nothing is seeded and no default credentials exist. (Set"
  echo "          ADMIN_EMAIL / ADMIN_PASSWORD in .env to seed your own.)"
fi
echo ""
echo "All accounts are equal: no admin role, no orgs — each account is its own"
echo "private workspace. Registration is open to anyone who can reach the port,"
echo "and password reset is not wired up for registered accounts."
echo "Re-run this wizard any time to change keys:  ./scripts/quickstart/wizard.sh"
ckpt "done — wizard complete"
