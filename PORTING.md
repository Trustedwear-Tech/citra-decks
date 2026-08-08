# Porting checklist

This repo was generated from a tree where the composers ran **inside** the Citra
platform. It compiles and every top-level import resolves, but it has not yet
been run standalone.

## 1. Deferred `graph/` imports — harmless, still worth removing

Three call sites defer-import `graph.embedding_service` for knowledge-graph
embedding cleanup, inside `try/except`:

- [ ] `folder_management.py:766`
- [ ] `services/enhanced_chunked_document_service.py:2986`
- [ ] `services/enhanced_chunked_document_service.py:4075`

The knowledge graph is not shipped, so these are dead branches that log a
warning. Delete them — do **not** vendor `graph/` to silence the log.

## 2. No host UI shell

`ui/composer` and `ui/printable` are the editors only. A standalone product
needs auth, theme and layout around them.

- [ ] Fork a shell from Citra-UI, or build a minimal one.

## 3. Not yet run end to end

- [ ] Bring up Mongo + Milvus + object storage and generate one deck from a
      real document set.
- [ ] Confirm the sandbox path that computes figures from spreadsheets works
      without the platform's job queue.

## 4. Chat surface

The tree carries `chat.py` / `query.py` because the composers share their
retrieval path. Decide whether to expose chat as a feature or trim it to the
retrieval functions the composers actually call.
