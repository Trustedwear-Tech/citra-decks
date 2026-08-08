# Vendored code

`citra-decks` is **independent**: it shares no repository with the
other Citra products and takes no dependency on a running Citra Decision
System. Independence is bought with duplication.

- `citra-*/` — six shared packages, each installable on its own.
- Backend modules vendored from `Citra-Service`.
- `ui/` — components/composer + components/printable, from `Citra-UI`.

**There is no merge path back.** Upstream fixes will not arrive
automatically. That is the accepted cost of independence, not an oversight.
