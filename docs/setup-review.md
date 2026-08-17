<!--
  Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
  Author: Rohit Kumar Chandan
  SPDX-License-Identifier: BUSL-1.1

  Licensed under the Business Source License 1.1. Non-production use is granted;
  production use requires a commercial licence until the Change Date, after
  which this file converts to Apache-2.0. See LICENSE at the repository root.
-->

# citra-decks setup — review

**Status:** review only, nothing changed. Findings are from reading the shipped
code.

**Context.** This is a presentation product. There is no ontology, no database to
connect, no org to seed — the whole setup should be *set two keys and go*. It is
already much closer to that than the decision system was, and most of what this
review finds is over-asking rather than under-delivering.

## What it does today

Four steps: `.env` → AI provider → image generation → bring up. Ten containers:
MongoDB (+init), Redis, the Milvus trio (etcd, MinIO, Milvus), MinIO, backend,
collaboration server, web. It ends at *"Open http://localhost:8094 and create
your first account."*

No org seeding, no admin bootstrap — self-signup. Correct for this product.

## Findings 1 and 2 — WITHDRAWN (product decision, 2026-08-11)

The first draft of this review proposed making the image backend a choice and
testing whether Milvus could be opt-in. Both are **rejected**, and the reasoning
matters more than the suggestions did.

**Everything the wizard asks for is required. There is no opt-in in this
product.**

- **OpenRouter** — drafting, grounding, vision.
- **Runware** — the imagery IS the product. A deck of text and charts is not what
  citra-decks is for, so "skip and get plain slides" is not a degraded mode worth
  offering at setup; it is a different, worse product. The code also backs this:
  `EDIT_CAPABLE_MODEL` means Runware is the only backend whose *edit* action
  works, so an alternative backend silently breaks the composers' edit button.
- **Milvus** — grounding decks in your own documents is core, not an add-on. The
  RAM floor it imposes is the cost of the product working properly.
- **MongoDB** — the application database. Not negotiable.
- **MinIO** — object storage, and there are TWO instances for two different
  jobs: `milvus-minio` is Milvus's own internal store (unpublished, private to
  it), and `minio` on 9022/9023 is the application's — uploaded documents,
  generated imagery, exports, the sandbox file cache. Both required; neither is
  a duplicate of the other.
- **Redis** — cache and coordination for the collaboration server.

So the correct setup shape is exactly what the wizard already does: ask for the
OpenRouter key, then the Runware key, and install the rest as required
infrastructure without asking. `IMAGE_GEN_PROVIDER=openai|comfyui` stays a
documented `.env` escape hatch for someone who knows they want it and accepts
losing edits — not a wizard branch.

What this means for the review: the wizard is **not** over-asking. It asks for
exactly the two things a user must supply, and everything else is a consequence
of what the product does. The findings below stand on their own; they are about
proving the install worked, not about asking for less.

## Finding 3 — no verify step

Setup ends at "open the URL". Nothing proves a deck can actually be generated —
the one thing the product does. citra-flows ends its install by authoring a
workflow, running it, and asserting `completed`; the decision system now runs a
`verify_install.py` on both paths. decks has neither.

**Suggested:** generate a one-slide deck at the end of `start.sh` and assert it
renders. It exercises the LLM key, the image key and the backend in one shot —
the three things most likely to be wrong — and turns "it started" into "it
worked."

## Finding 4 — no preflight

Nothing checks RAM against the documented 16 GB floor, disk, or bound ports
before a multi-minute build. Same gap the other two repos have;
`scripts/oss-install-test/preflight.sh` in Citra-AI is a working starting point.

## Finding 5 — smaller things

- **Vision is deliberately off** (`CRITIC_VISION_ENABLED=false`) with a good
  reason recorded in the wizard: it re-renders every slide through a vision model
  for a problem most decks do not have. That is a well-judged default — noted
  because it is the kind of thing later refactors quietly flip on.
- **The Runware model is asked, not hardcoded**, and defaults to the AIR id the
  repo relies on. Also well judged.
- **`make` is absent on Windows** and the bash fallback is documented, but the
  wizard assumes `bash`, `openssl`/`od` and `curl` — unverified on a bare
  Windows box.

## What is already right

Worth saying, because most of this review is "ask for less":

- One OpenRouter key covers drafting, grounding and vision — one key, one thing
  that can be wrong.
- It fails loud on a missing key rather than starting a stack that cannot draft.
- The wizard is re-runnable and preserves existing `.env` values.
- Defaults are explained where they are non-obvious, with the reasoning in
  comments rather than lost.

## Recommended order

| # | Change | Size | Why |
|---|---|---|---|
| 1 | Generate a one-slide deck as a verify step | S | Turns "started" into "works", exercising both keys and the backend |
| 2 | Preflight (RAM against the 16 GB floor, ports, disk) | S | Fail in 5s, not 10min — and the floor is real, since Milvus is required |

That is the whole list. The wizard asks for the right things in the right order;
what it lacks is proof that the install actually works, and an early check that
the machine can carry it.
