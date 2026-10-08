# Vireal v1.2 product handoff manifest

## Final artifacts

- PRD: `prd/prd_v1.2.html`
- Confirmed prototype: `prototype/prototype_v1.2.html`
- Product context: `server/PRODUCT.md`
- Approved design system: `server/DESIGN.md`
- Machine-readable design sidecar: `server/.impeccable/design.json`
- Surface direction: `annex/vireal-h5-surface.md`
- PostgreSQL schema draft: `annex/backend_schema_v1.2.sql`
- API examples: `annex/api_contract_v1.2.json`
- Mermaid sources: `flowcharts/01_catalog_browse_v1.2.mmd` through `flowcharts/05_admin_publish_v1.2.mmd`

## Version isolation

- `prd_v1.0.html`, `prd_v1.1.html`, `prototype_v1.0.html`, and `prototype_v1.1.html` remain in place as historical snapshots.
- Every v1.2 iframe references `prototype_v1.2.html` and enables Focus mode.
- The v1.2 PRD version selector links to v1.0, v1.1, and v1.2.

## Confirmed product decisions

- `prototype_v1.2.html` is the immutable visual authority.
- Adult authorization UI and backend blocking are disabled through a reversible configuration hook.
- Kiss and romance seed effects require two images; other seed effects require one.
- Category and effect counts are backend-driven; a new category creates three default effect records.
- Missing cover or preview media uses the numbered gradient fallback.
- Bottom navigation contains Discover, Works, and Account only; wallet remains accessible from the top balance and insufficient-balance recovery.
- Prices, balances, quotas, durations, and task states are backend truth.

## Validation evidence

- All seven Mermaid blocks embedded in the final PRD rendered successfully.
- All versioned v1.2 Mermaid source files parsed successfully.
- Five Focus-mode iframes are present and sandboxed.
- The PRD has no document-level horizontal overflow at 390 px or 1440 px.
- The prototype route matrix completed without page errors or horizontal overflow.
- `api_contract_v1.2.json` parses as valid JSON.
- `git diff --check` reports no whitespace errors.

## Implementation status

- Production H5 source is isolated under `h5/src`; v1.1 is retained in the build as an emergency fallback.
- SQLModel models and Alembic migration `f2a3b4c5d6e7` implement the catalog, variants, recommendations, managed media, coin account, immutable ledger, and task snapshots.
- The regenerated OpenAPI document and TypeScript client are the final interface source of truth.
- Full production traffic must still follow the documented backup, migration, backend, seed/grant, admin, H5, and smoke-check order.
