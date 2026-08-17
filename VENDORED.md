<!--
  Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
  Author: Rohit Kumar Chandan
  SPDX-License-Identifier: BUSL-1.1

  Licensed under the Business Source License 1.1. Non-production use is granted;
  production use requires a commercial licence until the Change Date, after
  which this file converts to Apache-2.0. See LICENSE at the repository root.
-->

# Vendored code

`citra-decks` is **independent**: it shares no repository with the
other Citra products and takes no dependency on a running Citra Decision
System. Independence is bought with duplication.

- `citra-*/` — six shared packages, each installable on its own.
- Backend modules vendored from `Citra-Service`.
- `ui/` — components/composer + components/printable, from `Citra-UI`.

**There is no merge path back.** Upstream fixes will not arrive
automatically. That is the accepted cost of independence, not an oversight.
