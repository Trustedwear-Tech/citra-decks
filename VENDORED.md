<!--
  Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
  Author: Rohit Kumar Chandan
  SPDX-License-Identifier: Apache-2.0

  Licensed under the Apache License, Version 2.0 (the "License"); you may not
  use this file except in compliance with the License. You may obtain a copy of
  the License at http://www.apache.org/licenses/LICENSE-2.0
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
