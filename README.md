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

> **Pre-release.** This tree was cut from a larger platform. It builds and
> imports cleanly, but it has not been run end to end as a standalone product,
> and there is no host UI shell yet. See `PORTING.md`.

## Why self-host this

Presentation and document tools are where confidential material goes to get
formatted. Board packs, incident reports, credit memos, patient summaries — the
things you would least like to paste into someone else's cloud.

Start on a hosted model API to evaluate. Point `LLM_BASE_URL` at your own vLLM
or Ollama endpoint for production, and nothing leaves your network.

## What is here

| Path | What |
|---|---|
| `presentation_api.py`, `slide_templates.py` | deck generation |
| `printable/` | A4 visual reports |
| `composer_*.py`, `services/edit_orchestrator.py` | the shared authoring engine |
| `ui/composer`, `ui/printable` | the editors |
| `citra-*/` | six shared packages, vendored |

It also carries the platform spine the composers need — RAG retrieval, document
ingestion, object storage, personal vaults. That is not accidental bloat: the
composers ground their output in your documents, and the retrieval path is the
product. See `VENDORED.md`.

## Requirements

Mongo · Milvus (vectors) · object storage (S3/MinIO) · a sandbox for computing
real figures from spreadsheets · an OpenAI-compatible model endpoint.

## Licence

Apache-2.0. See `LICENSE`.

Trustedwear Tech Private Limited · contact@citra-ai.com · https://citra-ai.com
