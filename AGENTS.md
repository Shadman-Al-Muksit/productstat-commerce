# ProductStat development

- Run backend, database and application validation in Ubuntu WSL. Source lives at `/mnt/d/Shadman-Desktop/Career/productstat`; use `scripts/env.sh` for isolated dependencies and local secrets. Do not modify sibling projects or reset the preserved database.
- Django owns price, stock, permission, payment and metric rules. Frontend code consumes `/api/v1/` and generated `src/lib/schema.d.ts`; regenerate the contract with `scripts/schema.sh` after API changes.
- Django endpoints require trailing slashes. The Next development proxy must preserve them; test through port3000 as well as direct port8001. Next uses webpack on this WSL1 mounted drive.
- Orders retain money/address snapshots. Keep payment, shipment, return, refund and inventory transitions distinct. Protect guest mutations with CSRF and guest tracking with tokens. Never log tokens, queries, customer payloads or credentials.
- Historical imports never execute live commerce side effects. Maintain stable source IDs, related-event identity and idempotent stock movement keys.
- Reporting uses event dates for activity and delivery cohorts for return rates. Keep cash separate from merchandise. Cache revisions must account for every committed canonical write, including out-of-order commits.
- Use `scripts/test-backend.sh`, `scripts/check.sh`, `scripts/schema.sh`, `scripts/async-check.sh`, `scripts/recovery-test.sh` and frontend Playwright tests as appropriate. Run load tests separately from builds and browser compilation to avoid competing workloads.
- Preserve ignored `.env`, runtime/database, backups and private uploads. Never commit their contents. Synthetic fixtures and local-only credentials must remain clearly labelled.
- Record measured results and external prerequisites in `docs/VALIDATION.md`. A local demo does not establish hosted operation, live payments, off-server backup delivery or production workload guarantees.
