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

## Quickstart

Requires Docker and Docker Compose. `make wizard` is the easiest first run — it
asks for a model-provider API key, writes `.env`, and brings up the full stack.

```bash
git clone <this-repo>
cd citra-decks
make wizard
```

Prefer to configure by hand? `make setup` (generate `.env`, start the data
stores, create the MinIO bucket) then `make start` (build and start the
backend, collaboration server, and web shell) do the same two phases
separately. `.env.example` is the template to start from. `make ps`,
`make logs` and `make down` manage the running stack; see the `Makefile` for
the full target list.

Once it's up:

| Service | URL |
|---|---|
| Web UI (Presentation / Visual Report / MS-Word Report) | http://localhost:8094 |
| Backend API (docs at `/docs`) | http://localhost:8093 |
| Real-time collaboration (Yjs/WebSocket) | ws://localhost:1234 |
| MinIO console | http://localhost:9003 |

Ports deliberately avoid the conventional 8081/8085/27017/19530/6379 —
citra-decks can run alongside another Citra product's stack on the same
machine without a port collision. Override any of them via `.env`
(`BACKEND_HOST_PORT`, `WEB_HOST_PORT`, `MONGODB_PORT`, `MILVUS_PORT`,
`MILVUS_METRICS_PORT`, `REDIS_HOST_PORT`) if you'd rather use the defaults.

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
anywhere in the product. Upload source documents into that folder (via each
composer's upload button) to ground generation in them; toggle "use data
source" off per-artifact to generate AI-only instead. The folder's contents are
visible from a button in each composer's toolbar.

## LLM configuration

Presentation and printable generation are pinned to **GLM-5.1** by default
(`PRESENTATION_LLM_MODEL` / `PRINTABLE_LLM_MODEL` in `.env`) — it produces
measurably better slide/report layouts than the platform's general-purpose
large-tier model. Routed through whichever provider `LLM_LARGE_BASE_URL` points
at; OpenRouter (`https://openrouter.ai/api/v1`) serves GLM-5.1 today, so that's
the default. Point it at your own OpenAI-compatible endpoint (vLLM, Ollama) for
production and nothing leaves your network — see `.env.example`.

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

Citra is a product of Trustedwear Tech Private Limited · Founder ex-Microsoft
(20+ yrs enterprise software) · Incubated at IIT Patna · Funded by Startup
India, MeitY & the Government of Bihar.

Rohit Kumar Chandan · Founder · rohit@citra-ai.com · https://citra-ai.com
