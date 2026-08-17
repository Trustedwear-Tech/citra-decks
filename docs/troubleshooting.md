<!--
  Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
  Author: Rohit Kumar Chandan
  SPDX-License-Identifier: BUSL-1.1

  Licensed under the Business Source License 1.1. Non-production use is granted;
  production use requires a commercial licence until the Change Date, after
  which this file converts to Apache-2.0. See LICENSE at the repository root.
-->

# Running citra-decks by hand, and fixing it when it breaks

The wizard does all of this for you. This page is for when it did not — so you
can bring each layer up yourself, see which one is unhappy, and fix that one
thing instead of re-running everything and hoping.

Read [the architecture section in the README](../README.md#architecture) first if
you have not: knowing which container is the UI, which is the API and which are
data makes everything below obvious rather than a list of incantations.

---

## Manual bring-up

Same order the wizard uses, because it is the order the dependencies demand.
Stop at the first step whose check fails — everything after it will fail too, and
for a reason you will misread.

### 0. Configuration

```bash
cp .env.example .env
```

Then set, at minimum:

| Variable | Why |
|---|---|
| `LLM_LARGE_API_KEY`, `EMBEDDING_API_KEY` | drafting and grounding. Nothing generates without these |
| `IMAGE_GEN_API_KEY` | Runware. Slides come out with no imagery without it |
| `JWT_SECRET` | any long random string; it signs your login sessions |

An **invalid** key is worse than a missing one: every container starts perfectly
and the install looks healthy right up until your first generation fails. If you
are debugging a failure that only appears at generation time, test the key
against the provider before suspecting anything else.

### 1. Data layer

```bash
docker compose up -d mongodb mongodb-init-rs redis milvus-etcd milvus-minio milvus minio
```

Seven containers. `mongodb-init-rs` will show as **Exited (0)** within a few
seconds — that is correct and is not a failure; it initiates the replica set and
stops. Check this layer (below) before going on.

### 2. MinIO bucket

Nothing except `setup.sh` creates this, which makes it the single most
missable step of a manual bring-up. Uploads fail without it.

```bash
docker run --rm --network citra-decks-network --entrypoint sh minio/mc:latest -c \
  "mc alias set local http://citra-decks-minio:9000 minioadmin minioadmin && \
   mc mb -p local/citra-documents"
```

Substitute `BUCKET_NAME`, `BUCKET_ACCESS_KEY` and `BUCKET_SECRET_KEY` from your
`.env` if you changed them.

### 3. Application layer

```bash
docker compose up -d --build backend collaboration-server web
```

First run builds three images and takes a while. `backend` will restart until
the data layer is genuinely ready — a few restarts here are normal; a permanent
loop is step 1 not being finished.

### 4. Milvus collections

```bash
docker compose exec -T backend python scripts/setup_milvus_schema.py
```

Idempotent — running it twice prints "already exists". **`start.sh` treats a
failure here as a warning and continues**, so it is entirely possible to have a
"successful" setup whose grounding does not work. If you saw *"generation may be
degraded"* scroll past, this is the step that did not happen.

---

## Checking each piece on its own

One command per container. Use these to find the unhappy layer instead of
reading ten containers of logs.

| What | Command | Expected |
|---|---|---|
| Mongo replica set | `docker compose exec -T mongodb mongosh --quiet -u "$MONGODB_USER" -p "$MONGODB_PASSWORD" --authenticationDatabase admin --eval 'rs.status().myState'` | `1` (PRIMARY) |
| Redis | `docker compose exec -T redis redis-cli ping` | `PONG` |
| MinIO + bucket | open `http://localhost:9023` (`minioadmin`/`minioadmin`) | the bucket is listed |
| Milvus | `curl -f http://localhost:9092/healthz` | `OK` |
| Milvus collections | `docker compose exec -T backend python scripts/setup_milvus_schema.py` | "successful" or "already exists" |
| Backend API | `curl http://localhost:8093/docs` | the OpenAPI page |
| Web UI | `curl -I http://localhost:8094` | `200` |
| Collaboration | browser devtools → Network → WS, while editing a deck | a live `ws://localhost:1234` connection |

Mongo requires authentication, so its check needs credentials — take
`MONGODB_USER` (default `root`) and `MONGODB_PASSWORD` from your `.env`. Without
them it answers `Command replSetGetStatus requires authentication`, which is the
server working correctly, not a fault.

`docker compose ps` shows everything at once; `docker compose logs -f backend`
is usually the informative one when the app layer misbehaves.

---

## Symptom → cause

| Symptom | Almost always | Fix |
|---|---|---|
| `backend` restarts forever | data layer not ready — usually the Mongo replica set never initiated | check `myState` is `1` (command above); re-run `docker compose up -d mongodb-init-rs` |
| Setup printed "generation may be degraded" | Milvus collections were never created; setup **continued anyway** | re-run step 4 |
| Decks draft, but every slide is text and charts | Runware key missing or wrong, or `IMAGE_GEN_PROVIDER` is not `runware` | check `IMAGE_GEN_API_KEY` in `.env`, then restart `backend` |
| Nothing generates at all | `LLM_LARGE_API_KEY` invalid or expired — looks identical to a healthy install until first use | test the key against your provider |
| Uploading a document fails | the MinIO bucket does not exist | step 2 |
| Deck opens, but edits do not sync between browsers | `collaboration-server` is down, or 1234 is blocked | `docker compose logs collaboration-server` |
| Grounding finds nothing in your documents | Milvus collections missing, or the document never finished processing | step 4, then re-upload |
| `mongodb-init-rs` shows Exited | **not a fault.** One-shot job; exit 0 is success | nothing |
| "port is already allocated" | another Citra stack is running | override in `.env` — see the port table in the README |
| Web loads but every call 502s | `backend` is not up | `docker compose logs backend` |

---

## Starting over

```bash
docker compose down          # keeps your data
docker compose down -v       # deletes the volumes too — decks, uploads, users
```

`down -v` is the real reset. It is also unrecoverable, so be sure.

---

## Still stuck

Useful things to include if you open an issue:

```bash
docker compose ps
docker compose logs --tail=100 backend
docker version
```

Plus which step above failed and what its check printed. That is usually enough
to identify the layer without any back-and-forth.
