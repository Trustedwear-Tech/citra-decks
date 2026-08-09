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

The stack has never actually been started (Mongo + Milvus + MinIO + backend +
collaboration server + web shell) — every check so far has been static
(import resolution, `@babel/parser`, a real `import main` boot test, dependency
resolution via `npm install`). `make wizard` should bring it up; the first real
run will surface whatever the static checks couldn't:

- [ ] Bring up the full stack and generate one deck from a real document set.
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
