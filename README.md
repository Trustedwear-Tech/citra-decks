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

### Easiest: the wizard

```bash
git clone https://github.com/Trustedwear-Tech/citra-decks.git
cd citra-decks
make wizard
```

It asks for one OpenRouter key, wires it to drafting, embeddings and vision,
optionally takes a Runware key for generated imagery, and brings the stack up.

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
| Vision (layout critique, OCR) | `qwen/qwen3-vl-32b-instruct` | |
| Image generation | *off* — Runware if you want it | the one capability OpenRouter does not serve, so it needs its own key |

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

Apache-2.0. See `LICENSE`.

Citra is a product of Trustedwear Tech Private Limited · Incubated at IIT
Patna · Funded by Startup India, MeitY & the Government of Bihar.

https://citra-ai.com
