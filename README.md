<!--
  Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
  Author: Rohit Kumar Chandan
  SPDX-License-Identifier: BUSL-1.1

  Licensed under the Business Source License 1.1. Non-production use is granted;
  production use requires a commercial licence until the Change Date, after
  which this file converts to Apache-2.0. See LICENSE at the repository root.
-->

# Citra Decks

**Sovereign presentations, visual reports and long-form documents — generated
from your own data, on your own infrastructure.**

Three composers, one engine:

- **Presentations** — slide decks grounded in your operational data
- **Visual reports** — print-ready A4 documents
- **Long-form documents** — Word-style reports drafted from your knowledge base

Every figure traces back to a source. Not a generic slide tool: the numbers come
from your files and your systems, and the deck can be regenerated when the data
changes.

## Why self-host this

Presentation and document tools are where confidential material goes to get
formatted. Board packs, incident reports, credit memos, patient summaries — the
things you would least like to paste into someone else's cloud.

Start on a hosted model API to evaluate. Point `LLM_LARGE_BASE_URL` at your own
vLLM or Ollama endpoint for production, and nothing leaves your network.

## How a deck gets made

Worth understanding before you run it, because it explains what the stack is
for. A generic slide tool asks a model to write plausible bullets. This asks a
different question — *what do your documents and spreadsheets actually say?*

```
   Goal ("Q3 collections review for the board")
     │
     ├── retrieval ──► your uploaded documents  ──► cited passages
     │                 (Milvus vector search)
     │
     ├── computation ─► your spreadsheets       ──► real figures
     │                 (Python in a Docker sandbox)
     │
     ▼
   Outline ──► slide/page generation ──► editable canvas ──► export
```

Two consequences drive most of the design:

- **The vector database is not optional.** Retrieval *is* the product. Without
  embeddings configured you have an expensive way to ask a model to guess —
  which is why the wizard now sets them up rather than leaving them blank.
- **Numbers are computed, not generated.** The model is asked for a small
  Python script, which runs in a sandbox against your actual Excel/CSV with the
  files mounted read-only; the **result** goes on the slide. A model asked to
  "sum column D" gives a confident wrong number. A model asked to write
  `df['D'].sum()` gives a correct one.

One more piece worth knowing: the deck is **rendered to an image, critiqued by
a vision model, and patched** from that critique. It is why the output does not
look like a wall of bullets. `ARCHITECTURE.md` has the full pipeline and the
module map for all three composers.

## Quickstart

### Prerequisites

| Need | Why |
|------|-----|
| **Docker Engine 24+** with Compose v2 | runs the whole stack |
| **16 GB+ RAM** | Milvus is the heaviest container |
| **An OpenRouter key** | drafting, grounding and vision |
| **A Runware key** | generated imagery — required, a few cents per image |

### Easiest: the wizard

```bash
git clone https://github.com/Trustedwear-Tech/citra-decks.git
cd citra-decks
make wizard
```

It asks for two keys — one OpenRouter key, wired to drafting, embeddings and
vision, and one Runware key for generated imagery — then brings the stack up.
Both are required; every model choice it writes is a quick-start default you
can change in `.env` afterwards.

> **No `make`?** It is not installed by default on Windows, and the targets are
> thin wrappers — run the scripts directly instead:
> `bash scripts/quickstart/wizard.sh`

### Or by hand — two phases

```bash
make setup                     # or: bash scripts/quickstart/setup.sh
#   generates .env, starts the data stores, creates the MinIO bucket

# set your key in .env  ->  LLM_LARGE_API_KEY / EMBEDDING_API_KEY

make start                     # or: bash scripts/quickstart/start.sh
#   builds and starts the backend, collaboration server and web shell
```

`.env.example` is the template. `make ps`, `make logs` and `make down` manage
the running stack; see the `Makefile` for the full target list.

If either phase fails, [`docs/troubleshooting.md`](docs/troubleshooting.md)
brings each layer up by hand with a check after every step, so you can find the
one unhappy container instead of re-running the lot.

Once it's up:

| Service | URL |
|---|---|
| Web UI (Presentation / Visual Report / MS-Word Report) | http://localhost:8094 |
| Backend API (docs at `/docs`) | http://localhost:8093 |
| Real-time collaboration (Yjs/WebSocket) | ws://localhost:1234 |
| MinIO console | http://localhost:9023 |

Ports deliberately avoid the conventional 8081/8085/27017/19530/6379/9002 —
citra-decks can run alongside another Citra product's stack on the same
machine without a port collision. Override any of them via `.env`
(`BACKEND_HOST_PORT`, `WEB_HOST_PORT`, `MONGODB_PORT`, `MILVUS_PORT`,
`MILVUS_METRICS_PORT`, `REDIS_HOST_PORT`, `MINIO_API_PORT`,
`MINIO_CONSOLE_PORT`) if you'd rather use the defaults.

There is no seeded account — register your first user from the web UI's sign-up
screen. `api/local_auth.py` issues its own JWTs (bcrypt-hashed passwords, a
`users` collection); there is no separate user-service to stand up.

## Architecture

Ten containers in three layers. Worth a minute now — when something misbehaves,
knowing which layer it lives in is most of the diagnosis.

| Container | Layer | What it does | Port |
|---|---|---|---|
| `web` | edge | the UI — Presentation, Visual Report, MS-Word Report | **8094** |
| `backend` | app | the API: drafting, composing, image generation, exports. OpenAPI at `/docs` | **8093** |
| `collaboration-server` | app | real-time multi-user editing (Yjs over WebSocket) | **1234** |
| `mongodb` | data | decks, reports, users — all application state | 27018 |
| `mongodb-init-rs` | data | one-shot: initiates the replica set, then exits | — |
| `redis` | data | cache, and collaboration coordination | 6382 |
| `minio` | data | uploaded documents, generated imagery, exports | 9022 / **9023** console |
| `milvus` | data | vector store — grounds drafts in your uploaded documents | 19531 / 9092 |
| `milvus-etcd` | data | Milvus's metadata store, internal to it | — |
| `milvus-minio` | data | Milvus's own object store — **not** the same as `minio` above | — |

Two things that look like faults and are not: **`mongodb-init-rs` showing
`Exited (0)` is success** — it is a one-shot job — and the **two MinIO
containers are not duplicates**; one is Milvus's private store, the other holds
your uploads and exports.

Everything here is required. There is no cut-down mode: the imagery and the
document grounding are what the product is.

### What depends on what

```
  milvus-etcd ──┐
                ├──> milvus ───┐
  milvus-minio ─┘              │
  mongodb ──> mongodb-init-rs ─┤
  redis ───────────────────────┼──> backend ──┬──> web                   (8094)
  minio ───────────────────────┘              └──> collaboration-server  (1234)
```

That is also the manual bring-up order, and it explains the most common
confusion: a `backend` that restart-loops is nearly always a **data layer**
problem, not a backend one.

### How a request flows

Your browser loads `web` on **8094**, which calls `backend` on **8093** for
everything — drafting, images, exports. The editor separately holds a WebSocket
to `collaboration-server` on **1234**.

Those being two different connections is useful to know: if a deck loads and
renders but live edits do not sync between browsers, only the collaboration
server is implicated. Nothing else needs looking at.

### When it does not work

[`docs/troubleshooting.md`](docs/troubleshooting.md) has the manual bring-up
step by step, a one-line health check per container, and a symptom-to-cause
table. Written for exactly the case where the wizard failed and you want to
bring each layer up yourself.

## What is here

| Path | What |
|---|---|
| `presentation_api.py`, `slide_templates.py` | deck generation |
| `printable/` | A4 visual reports |
| `composer_*.py`, `services/edit_orchestrator.py` | the shared authoring engine |
| `ui/composer`, `ui/printable` | the editors |
| `App.js`, `screens/`, `components/`, `contexts/` | the host shell — landing page, auth, folder-per-artifact flow |
| `collaboration-server/` | real-time co-editing (Yjs + WebSocket), its own container |
| `api/local_auth.py` | register/login/forgot-password — no external auth service needed |
| `citra-*/` | six shared packages, vendored |

It also carries the platform spine the composers need — RAG retrieval, document
ingestion, object storage, personal vaults. That is not accidental bloat: the
composers ground their output in your documents, and the retrieval path is the
product. See `VENDORED.md`.

### Folder-per-artifact

Every presentation, visual report, and long-form document gets exactly one
auto-created folder the moment you start it — there is no folder picker
anywhere in the product. Source documents in that folder ground the
generation; toggle "use data source" off per-artifact to generate AI-only
instead. The folder's contents are visible from a button in each composer's
toolbar.

Two ways in, both verified end to end (upload → extract → embed with bge-m3 →
retrievable through the composers' vault prefetch):

**The upload button in each composer** posts to `POST /v2/documents`. Driving
it directly takes the same four fields the UI sends:

```bash
curl -X POST http://localhost:8093/v2/documents \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@policy.md" -F "document_id=$(uuidgen)" \
  -F "filename=policy.md" -F "folder_id=<id>"
```

**`POST /from-url`** fetches a page instead of taking a file:

```bash
curl -X POST http://localhost:8093/from-url \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"url":"https://example.com/policy","folder_id":"<id>","topic":"policy"}'
```

It accepts **HTML only** — a `text/plain` or raw-markdown URL is rejected on
content type.

> Ignore the commented-out `@router.post("/upload")` in
> `api/chunked_documents.py`. It is a superseded v1 handler whose service
> method no longer exists; `/v2/documents` replaced it. It is dead code, not a
> missing feature.

## Model configuration

The wizard asks for **one OpenRouter key** and wires it to all three roles.
Every default is open-weights:

| Role | Default | Notes |
|---|---|---|
| Drafting | `deepseek/deepseek-v4-pro` | `LLM_LARGE/MEDIUM/SMALL_MODEL` |
| Slide + report layout | `z-ai/glm-5.1` | `PRESENTATION_LLM_MODEL` / `PRINTABLE_LLM_MODEL` — measurably better structure than the general-purpose tier |
| Embeddings | `baai/bge-m3` at 768 | the client sends `dimensions`, so it returns 768 rather than its native 1024, matching the Milvus collection |
| **Image generation** | **required — Runware, `runware:400@1`** | cover art and section imagery. Its own key: the one thing the OpenRouter key does not cover |
| Vision (layout critique) | `qwen/qwen3-vl-32b-instruct` — **off** | `CRITIC_VISION_ENABLED=false`. Turn on only if you see glitches |

**Image generation is required, and the wizard will not continue without it.**
Without imagery the composers still generate, but the output is plain — no
cover art, no section visuals, just text and charts. That is the largest
single difference between a deck that looks designed and one that reads like
an outline, and it costs a few cents an image, so declining saves nothing
worth having.

**The wizard configures Runware and nothing else** — deliberately. It is what
this product has actually been built and tested against, and it is the only
backend whose image **edit** action works, so it is the one configuration
guaranteed to behave on a first run. Two other backends are supported in code
and documented in `.env.example`, and switching to either is an `.env` edit
after setup rather than another trip through the wizard:

| `IMAGE_GEN_PROVIDER` | What it is | Editing |
|---|---|---|
| `runware` | What the wizard sets. `IMAGE_GEN_API_KEY` and you are done. | ✅ |
| `openai` | Any OpenAI-compatible `/images/generations` endpoint — Together, Fal, DeepInfra, Nebius, or your own — which is how you run **FLUX** without a Runware account. Set `IMAGE_GEN_BASE_URL` and `IMAGE_GEN_MODEL` too. | ✗ |
| `comfyui` | Self-hosted ComfyUI; nothing leaves your network. | ✗ |

If you genuinely want imagery off, that too is an `.env` decision — set the
variables yourself and skip the wizard.

**Leave vision off until you need it.** It is a separate thing from image
generation: it re-renders each finished slide and sends the picture to a
vision model to find overlaps and patch the layout. That is real time and
tokens on every generation, for a problem most decks do not have. If you do
see elements overlapping or text running off a slide, set
`CRITIC_VISION_ENABLED=true` — the credentials are already configured.

Everything routes through whichever endpoint the matching `*_BASE_URL` points
at, so **swapping is an `.env` edit, not a migration**: point them at your own
vLLM or Ollama and nothing leaves your network.

> **Changing the embedding model means re-ingesting**, even at the same
> dimension. Vectors written by one model do not share an embedding space with
> another model's queries, so previously uploaded documents quietly stop
> matching rather than failing loudly.

## Requirements

Docker + Docker Compose (the quickstart stack: Mongo, Milvus, MinIO, Redis,
the backend, the collaboration server, the web shell) · an OpenAI-compatible
model endpoint for generation.

## Community

**Discord:** https://discordapp.com/channels/1519703038724669551/1519703039416467518
— shared with Citra Flows and Citra Projects. Questions, setup issues, or
what a real deployment needs that isn't here yet.

## Licence

Business Source License 1.1 (BUSL-1.1) -- source-available, not open source.
Free to use, copy, and modify for any non-production purpose: development,
testing, security review, internal evaluation, and pilots of up to 90 days on
your own data. Production use requires a commercial licence. Each released
version converts to Apache License 2.0 four years after its release date --
automatically, with no action required from us and no way for us to withdraw
it. For v0.1.0 the Change Date is **2030-08-17**. The vendored Citra Common
packages (`citra-auth/`, `citra-cache/`, `citra-llm/`, `citra-mongo/`,
`citra-queue/`, `citra-service-utils/`) are Apache-2.0 and stay Apache-2.0.
See `LICENSE` and `NOTICE`.

Citra is a product of Trustedwear Tech Private Limited · Incubated at IIT
Patna · Funded by Startup India, MeitY & the Government of Bihar.

https://citra-ai.com
