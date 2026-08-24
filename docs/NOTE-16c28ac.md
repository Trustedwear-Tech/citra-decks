<!--
  Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
  Author: Rohit Kumar Chandan
  SPDX-License-Identifier: Apache-2.0

  Licensed under the Apache License, Version 2.0 (the "License"); you may not
  use this file except in compliance with the License. You may obtain a copy of
  the License at http://www.apache.org/licenses/LICENSE-2.0
-->

# Note on commit 16c28ac

`16c28ac fix(ingest): report the chunk/vector counts that were actually
written` describes a three-file change. The commit contains fifty.

It was made with `git add -A` in a session that did not check `git status`
first, so it swept up work that was already sitting uncommitted in the tree
alongside the intended fix.

**Actually written by that change (3 files):**

- `document_manager.py` — `/from-url` read `result['total_chunks']` and
  `result['total_vectors']`, but the producer returns `vectors_created` and
  `chunks`; both `.get(...)` calls fell through to 0, so a successful ingest
  reported that nothing had been indexed.
- `README.md`, `PORTING.md` — documented that local file upload does not
  exist in this tree, and that `/from-url` is the working ingestion path.

**Swept in, and NOT part of that change (47 files):**

- 44 deletions — `agentic_rag/`, `text_cleanup.py`,
  `services/vault_sharing_service.py`, `verification/`, a batch of tests, and
  assorted binaries. These belong to the carve-out cleanup that was in
  progress in the working tree; they are the same class of removal as
  `f5b15ad`'s "drop dead UI", and they were intended — just not by this
  commit.
- `.gitignore`, `ui/composer/PresentationSharedToolbar.js`,
  `ui/printable/PrintableSharedToolbar.js` — likewise pre-existing edits.

Nothing was lost and no history was rewritten; the record is simply wider
than its subject line claims. Kept as-is deliberately rather than
force-pushing a public branch to tidy it.
