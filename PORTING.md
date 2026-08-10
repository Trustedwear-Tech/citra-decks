# Porting checklist

This repo was generated from a tree where the composers ran **inside** the Citra
platform. It now has a host shell, a local auth backend, and a docker-compose
quickstart — see `README.md` for how to run it. Remaining items:

## 1. Deferred `graph/` imports — harmless, still worth removing

Two call sites defer-import `graph.embedding_service` for knowledge-graph
embedding cleanup, inside `try/except` (a third, in `folder_management.py`, was
removed along with the rest of that file's folder-list/update/delete/stats
endpoints when the folder-per-artifact model replaced manual folder
management):

- [ ] `services/enhanced_chunked_document_service.py:2986`
- [ ] `services/enhanced_chunked_document_service.py:4075`

The knowledge graph is not shipped, so these are dead branches that log a
warning. Delete them — do **not** vendor `graph/` to silence the log.

## 2. Not yet run end to end

The stack has now been brought up from a clean clone and driven partway. What
that first real run established, and what it left open:

- [x] **Bring the full stack up.** Mongo + Milvus + MinIO + backend +
      collaboration server + web shell all start and report healthy from
      `setup.sh` → `start.sh` on a fresh clone. It surfaced four bugs, all
      fixed: a stale `mongodb_data` volume making Mongo reject the generated
      password (and the readiness loop blaming the replica set for it), the
      MinIO port colliding with a sibling Citra stack, a banner printing
      hardcoded ports, and the wizard configuring the LLM but never
      embeddings.
- [x] **Ingest → embed → retrieve.** A document fetched through
      `POST /from-url` is chunked, embedded with `baai/bge-m3` at 768, written
      to Milvus, and comes back from the composers' vault prefetch for a
      related query. The grounding path works.
- [x] **Local file upload works.** Verified: `POST /v2/documents` with
      `file`, `document_id`, `filename` and `folder_id` returns
      `vectors_created: 1, text_extracted: true`, stores the original in
      MinIO, and the content comes back through the composers' vault prefetch
      for a related query. `hooks/useDocumentUpload.js` is what the composer
      upload buttons call.

      An earlier revision of this file claimed upload did not exist. That was
      wrong: it read the commented-out `@router.post("/upload")` in
      `api/chunked_documents.py` as the upload path. That handler is a
      superseded v1 whose service method was removed; `/v2/documents`
      replaced it. Worth deleting so it stops misleading readers.
- [ ] Generate one full deck end to end from a real document set.
- [ ] Confirm the sandbox path that computes figures from spreadsheets works
      without the platform's job queue.
- [ ] Confirm two browser tabs editing the same document actually sync through
      the collaboration server (Yjs/WebSocket) — enabled but unverified live.

## 3. Chat surface — resolved

`chat.py` / `query.py` are kept as importable-but-unmounted libraries, not
exposed as a feature — `document_manager.py`'s internet-research grounding path
(`services/internet_prefetch.py`) depends on functions from `document_manager.py`
that in turn need `chat.py`'s `get_chat_session_by_id`. No HTTP chat surface is
mounted in `main.py`.
