<!--
  Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
  Author: Rohit Kumar Chandan
  SPDX-License-Identifier: BUSL-1.1

  Licensed under the Business Source License 1.1. Non-production use is granted;
  production use requires a commercial licence until the Change Date, after
  which this file converts to Apache-2.0. See LICENSE at the repository root.
-->

# Plan: architecture + manual setup for citra-decks

**Status:** plan. Nothing changed yet.

**Why.** If the wizard fails, a check that says "it's broken" does not help — the
user needs to know what the pieces ARE, which one broke, and how to run it by
hand. That is documentation, not tooling, and it is the higher-value work.

**What already exists** (better than expected, and none of it should be
rewritten): a two-phase by-hand path (`make setup` / `make start` with bash
equivalents), a service/URL table for the four user-facing endpoints, the port
override variables, and a clear note that there is no seeded account because
`api/local_auth.py` issues its own JWTs.

**The gap.** Ten containers run; four are documented. Nothing says what the other
six are for, what depends on what, or how to check any single piece in isolation.
A user whose `make start` failed has a wall of compose output and no map.

---

## Part 1 — An architecture section in the README

Three layers, stated plainly. This is the piece that makes everything else
diagnosable.

### What to document

| Container | Layer | What it is for | Published |
|---|---|---|---|
| `web` | edge | the UI you use — Presentation, Visual Report, MS-Word Report | **8094** |
| `backend` | app | the API: drafting, composing, image generation, exports. `/docs` for OpenAPI | **8093** |
| `collaboration-server` | app | real-time multi-user editing (Yjs over WebSocket) | **1234** |
| `mongodb` | data | decks, reports, users, all application state | 27018 |
| `mongodb-init-rs` | data | **one-shot.** Initiates the replica set, then exits 0 — it is SUPPOSED to be "Exited" | — |
| `redis` | data | cache and collaboration coordination | 6382 |
| `minio` | data | uploaded documents, generated imagery, exports | 9022 / **9023** console |
| `milvus` | data | vector store — grounding drafts in your uploaded documents | 19531 / 9092 |
| `milvus-etcd` | data | Milvus's metadata store. Internal to Milvus | — |
| `milvus-minio` | data | Milvus's own object store. **Not** the same as `minio` above | — |

Two things this table alone prevents: someone "fixing" `mongodb-init-rs`
because it shows as Exited (it is a one-shot job and that is success), and
someone assuming the two MinIO containers are a duplicate and removing one.

### The dependency graph, as compose actually declares it

```
  milvus-etcd ─┐
               ├─> milvus ─┐
  milvus-minio ─┘          │
  mongodb ─> mongodb-init-rs ─┤
  redis ──────────────────────┼─> backend ─┬─> web                  (8094)
  minio ──────────────────────┘            └─> collaboration-server (1234)
```

Which gives the manual bring-up order for free, and explains why `backend`
restarting in a loop is almost always a data-layer problem rather than a backend
problem.

### The request path

Worth one short paragraph: the browser talks to `web` (8094), which calls
`backend` (8093) for everything; the editor holds a second, separate WebSocket to
`collaboration-server` (1234). So "the deck loads but live editing doesn't sync"
localises immediately to one container — that is the point of documenting it.

---

## Part 2 — A manual bring-up path

Not a replacement for the wizard: the path you take when the wizard failed and
you need to see each layer come up on its own.

```bash
cp .env.example .env          # then set LLM_LARGE_API_KEY / EMBEDDING_API_KEY
                              # and IMAGE_GEN_API_KEY (Runware)

# 1. data layer
docker compose up -d mongodb mongodb-init-rs redis milvus-etcd milvus-minio milvus minio

# 2. check it before going further  (see Part 3)

# 3. application layer
docker compose up -d --build backend collaboration-server web

# 4. Milvus schema — the backend needs its collections to exist
docker compose exec -T backend python scripts/setup_milvus_schema.py
```

Each step gets a paragraph on what should be true afterwards, so a user can stop
at the first thing that is wrong instead of reading ten containers of logs.

The MinIO bucket creation that `setup.sh` performs must be written out here too —
it is the least discoverable step and nothing else creates the bucket.

---

## Part 3 — Check each piece independently

One command per container, so "is X actually working?" is answerable without
reading logs.

| Check | Command |
|---|---|
| Mongo replica set is PRIMARY | `docker compose exec -T mongodb mongosh --quiet --eval 'rs.status().myState'` → `1` |
| Redis answers | `docker compose exec -T redis redis-cli ping` → `PONG` |
| MinIO is up + bucket exists | console at `:9023`, or `mc ls` |
| Milvus is serving | `curl -f http://localhost:9092/healthz` |
| Milvus schema created | `docker compose exec -T backend python scripts/setup_milvus_schema.py` — it is idempotent and says "already exists" |
| Backend is alive | `curl http://localhost:8093/docs` |
| Web is served | `curl -I http://localhost:8094` |
| Collaboration | WebSocket connect to `ws://localhost:1234` |

---

## Part 4 — Symptom → cause

The table a user actually reaches for. Every row is a real failure mode from the
code, not invented:

| Symptom | Likely cause | Fix |
|---|---|---|
| `backend` restart-loops | data layer not ready — usually Mongo replica set not initiated | check `rs.status()`; re-run `mongodb-init-rs` |
| Setup said "generation may be degraded" | Milvus schema not created — **`start.sh` warns and continues**, so this is easy to miss | re-run `setup_milvus_schema.py` |
| Deck drafts, but has no imagery | Runware key wrong/absent, or `IMAGE_GEN_PROVIDER` not `runware` | check `IMAGE_GEN_API_KEY` |
| Drafting fails entirely | `LLM_LARGE_API_KEY` wrong or expired — **an invalid key looks exactly like a working install until first use** | test the key against the provider |
| Deck loads, live editing does not sync | `collaboration-server` down, or 1234 blocked | check that container specifically |
| Uploads fail | MinIO bucket missing — created by `setup.sh` and by nothing else | create it |
| Port already in use | another Citra stack | override via `.env` (the vars are already documented) |
| `mongodb-init-rs` shows Exited | **not a fault** — one-shot job, exit 0 is success | nothing |

---

## Part 5 — Where this lives

- **README** gets the architecture table, the dependency diagram and the request
  path. It is what a first-time reader needs, and it is short.
- **`docs/troubleshooting.md`** gets Parts 2-4 in full. Too long for the README,
  and the README should link to it from the Quickstart section so it is found at
  the moment it is needed.

## On the verify step

Deprioritised, and the reasoning is worth keeping: a check that reports failure
without telling you how to fix it is not much help. These docs are the more
valuable half.

They compose, though — verification localises the fault ("the catalogue is empty
and here is the usual cause"), and the troubleshooting table remediates it. If
verification is ever added, it should point INTO Part 4 rather than just
reporting a red line. Docs first.

## Order

| # | Work | Size |
|---|---|---|
| 1 | Architecture table + dependency graph in README | S |
| 2 | `docs/troubleshooting.md` — manual bring-up, per-piece checks, symptom table | M |
| 3 | Link it from Quickstart | XS |

All documentation. No code changes, so nothing can regress.
