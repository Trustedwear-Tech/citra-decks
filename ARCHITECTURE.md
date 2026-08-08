# Architecture

Three composers on one authoring engine, grounded in your own documents and
spreadsheets.

> **Pre-release.** The tree compiles and every top-level import resolves, but it
> has not been run standalone and has no host UI shell. See `PORTING.md`.

---

## 1. What "grounded" means here, and why it drives everything

A generic slide tool asks a model to write plausible bullets. This asks a
different question: *what do your documents and spreadsheets actually say?*

```
   Goal ("Q3 collections review for the board")
     │
     ├── retrieval ──► your uploaded documents  ──► cited passages
     │                 (Milvus vector search)
     │
     ├── computation ─► your spreadsheets       ──► real figures
     │                 (Python in a sandbox)
     │
     ▼
   Outline ──► slide/page generation ──► editable canvas ──► export
```

Two consequences that explain most of the design:

**A vector database is not optional.** Retrieval is the product. Without it you
have an expensive way to ask a model to guess.

**Numbers are computed, not generated.** `services/compute_fact_tool.py` and
`services/structured_sandbox.py` ask the model for a small Python script, run it
in a Docker sandbox against the user's actual Excel/CSV/JSON with the files
mounted at `/workspace/input/`, and put the **result** on the slide. A model
asked to "sum column D" will produce a confident, wrong number; a model asked to
write `df['D'].sum()` produces a correct one.

---

## 2. The three composers

| Composer | Output | Backend |
|---|---|---|
| **Presentation** | slide decks | `presentation_api.py`, `slide_templates.py` |
| **Visual report** | print-ready A4 | `printable/` |
| **Document** | Word-style long-form | the composer/report path |

They are three faces on one engine, not three products:

- `composer_query.py` — retrieval and structured-data prefetch
- `composer_context.py` — assembling what the model sees
- `services/edit_orchestrator.py` — the shared edit pipeline
- `services/storyboard.py` — outline planning
- `services/agent_deck_editor.py` / `agent_report_editor.py` — whole-artifact edits
- `services/visual_critique.py` — render, look at it, patch what is wrong

That last one is worth knowing about: the deck is rendered to an image, a vision
model critiques the layout, and the critique becomes patches. It is why output
does not look like a wall of bullets.

---

## 3. The spine, and why it is here

The repo carries more than the composers: document ingestion, folders/vaults,
RAG, object storage, persona. `VENDORED.md` records the provenance.

This is **not** accidental bloat. Tracing the composers against the platform
they came from, they touch **92 of 227 backend modules** — they are faces on a
shared spine rather than a separable module. Carving further would mean weeks
untangling a monolith, and a half-carved tree fails at runtime rather than at
import.

So the trade was made explicitly: duplicate the spine, ship something that
works, and accept that upstream fixes will not arrive automatically.

| Layer | Modules |
|---|---|
| Retrieval | `agentic_rag/`, `rag/`, `llamaindex_query_engine.py`, `reranker.py` |
| Documents | `document_manager.py`, `file_manager.py`, `text_extractors.py` |
| Vaults/folders | `folder_management.py`, `dept_library.py` |
| Storage | `bucket.py`, `storage_backend.py` |
| Voice | `persona.py` |

---

## 4. Data stores

| Store | Used for |
|---|---|
| **Mongo** | decks, reports, documents, folders |
| **Milvus** | document vectors — retrieval, i.e. the grounding |
| **Object storage** (S3/MinIO) | uploads, generated images, exports |
| **Sandbox** (Docker) | computing figures from spreadsheets |

No Postgres. No queue.

> Changing `EMBEDDING_MODEL` or `EMBEDDING_DIMENSION` **invalidates existing
> vectors**. Re-ingest afterwards, or retrieval silently returns nonsense from a
> mismatched vector space — no error, just worse citations.

---

## 5. Models

Anything OpenAI-compatible. Three roles, and they can be different models:

| Role | Variable | Notes |
|---|---|---|
| Authoring | `LLM_*` | outline, slide and section text |
| Embeddings | `EMBEDDING_*` | retrieval quality tracks this closely |
| Vision | `VISION_*` | layout critique; optional |

For production, point them inside your network (vLLM, TGI, Ollama) and no
document, prompt or figure leaves your infrastructure.

---

## 6. Honest limitations

- **Not yet run standalone.** It compiles; that is not the same thing.
- **No host UI shell.** `ui/composer` and `ui/printable` are the editors only.
- **The sandbox is required for real numbers.** Without Docker access, the
  compute path degrades and figures come from the model — which is exactly the
  failure mode this design exists to prevent. Check `PORTING.md` before
  disabling it.
- **Retrieval quality tracks your embedding model.** Small models are cheap and
  noticeably worse at citation.
- **Three dead `graph/` imports remain**, inside `try/except`. Harmless, listed
  in `PORTING.md`.

---

## Licence

Apache-2.0. See `LICENSE`. Copyright (c) 2024–2026 Trustedwear Tech Private
Limited.
