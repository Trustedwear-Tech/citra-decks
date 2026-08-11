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

## Finding 1 — Runware is presented as the only option; the code supports three

`image_gen_providers.py` implements **three** backends, selected by
`IMAGE_GEN_PROVIDER`:

| Provider | What it is |
|---|---|
| `runware` | cloud, via the Runware SDK |
| `openai` | **any OpenAI-compatible `/images/generations` endpoint** — Together, Fal, DeepInfra, Nebius, or your own server |
| `comfyui` | self-hosted ComfyUI |

Its own docstring says the second is *"how you point citra-decks at a FLUX model
without using Runware."*

The wizard hard-fails on an empty Runware key and writes
`IMAGE_GEN_PROVIDER=runware` unconditionally. It does mention the alternatives in
prose — but its failure message tells the user that if they want a different
backend they should *"set the IMAGE_GEN_ variables yourself in .env and skip this
wizard."* A setup wizard whose answer to a supported configuration is "don't use
the wizard" is the finding.

**There is a real constraint behind the default**, and it is well documented in
the code: `EDIT_CAPABLE_MODEL` — Runware is the only backend whose *edit* action
works, so swapping breaks the composers' edit button. That justifies Runware as
the **recommended default**. It does not justify it being the only path.

**Suggested:** make step 3 a choice — Runware (recommended, edit works), any
OpenAI-compatible endpoint (bring your own key + base URL), self-hosted ComfyUI,
or skip for now (text and charts only, imagery off). Say plainly that only
Runware supports slide editing. Skipping should be permitted: the wizard's own
text already admits decks render "text and charts only" without it, so the
degraded path exists and works.

## Finding 2 — Milvus is unconditional and it is the heaviest thing in the box

`setup.sh` starts `milvus-etcd milvus-minio milvus` every time. The README's
16 GB floor is attributed to Milvus specifically.

Milvus serves RAG — grounding a draft in documents the user uploaded. A user
whose first act is "make me a deck about X" from a prompt does not need it for
that. And `start.sh` already treats a Milvus schema failure as non-fatal, warning
that *"generation may be degraded"* — so a degraded-without-Milvus mode is
already an acknowledged state.

**Worth testing, not assuming:** can a deck be generated end to end with the
Milvus trio stopped? If yes, an opt-in prompt ("Do you want to ground decks in
your own documents? Adds ~3 containers and most of the RAM requirement") would
cut the entry cost of this product substantially. If no, the 16 GB floor is
irreducible and should be stated harder up front. I have not run this, so it is a
question, not a recommendation.

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
| 1 | Offer the three image backends + skip | S | The code already supports it; the wizard is the only thing insisting on Runware |
| 2 | Generate a one-slide deck as a verify step | S | Turns "started" into "works", exercising all three keys |
| 3 | Test whether Milvus can be opt-in | M | Could remove most of the RAM floor for the common case |
| 4 | Preflight | S | Fail in 5s, not 10min |

None of this is structural. Unlike the decision system, decks does not have a
path that silently fails to finish — it just asks for more than it needs.
