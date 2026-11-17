# Operations and recovery

## Verified deployment scope

[GitHub Actions run 44015893889](https://github.com/Shadman-Al-Muksit/productstat-commerce/actions/runs/44015893889) built and started the Compose stack on Ubuntu, served the standalone storefront/assets through Caddy HTTPS, completed a synthetic COD/return/refund/report workflow, and restored an encrypted database/private-media backup. The evidence used a disposable localhost certificate and a small synthetic fixture. See [validation results](VALIDATION.md) and the [container smoke](evidence/ci-container-smoke.json) and [restore](evidence/ci-container-restore.json) records.

A public server/domain, merchant credentials, external SMTP and an off-server backup destination remain unconfigured. The tested container deployment is reproducible; a publicly hosted shop has not been established. Changes after the referenced CI commit require their own final regression.

## Local runtime

`scripts/env.sh` loads the ignored local `.env` and selects isolated Linux dependencies. PostgreSQL 17 uses port 55433; Redis 56379; Django 8001; Next.js 3000. These do not reuse the sibling Campus ERP ports.

Use `bash scripts/dev.sh` for the API, interface, worker and scheduler. For the optimized local frontend, build it first, then use `bash scripts/dev.sh --preview`. These use local demo settings. Ctrl+C stops the launcher's owned application process groups; database persistence remains. Never remove the runtime cluster to fix a migration or schema error.

## Server deployment

Use an Ubuntu host with Docker Engine and the Compose plugin. From the repository checkout:

1. Copy `.env.production.example` to `.env.production`, replace every secret/domain placeholder and choose the company/demo flags. Keep the file out of source control. Database credentials used by PostgreSQL and the application must match.
2. Point the chosen public domain's DNS at the host and allow ports 80/443. Database and Redis have no host-published ports.
3. Run `docker compose --env-file .env.production config --quiet`. Confirm the intended domain, volumes and backup-key path before startup.
4. Run `docker compose --env-file .env.production up -d --build --wait --wait-timeout 120`.
5. Create private staff credentials with the correct application roles. For a synthetic demo, run `seed_demo` with separate strong `DEMO_PASSWORD` and `DEMO_VIEWER_PASSWORD`; expose only the analyst account publicly. Do not seed synthetic trading history into a real company's database.
6. Check readiness, logs, failed import/outbox states and a controlled end-to-end transaction. Confirm shipping charges, merchandise-exclusive tax rate and return settings before a company COD pilot.

Caddy terminates HTTPS. Django validates production secrets/hosts and uses secure session/CSRF cookies. The internal readiness endpoint is exempt from HTTPS redirects for container probes and checks PostgreSQL/Redis without returning credentials or exception details. Request logs carry IDs and omit query strings and customer payloads; Gunicorn's full-request access logging is disabled.

With `PRODUCTSTAT_DEMO=1`, external notifications are suppressed even if SMTP is configured. A company pilot needs `PRODUCTSTAT_DEMO=0` and a configured SMTP backend/provider if notifications are required. Online payment remains unavailable without merchant credentials. Sandbox initiation is confined to the demo, and sandbox records cannot authorize real-company preparation or dispatch. Live collection requires separate merchant validation and the `SSLCOMMERZ_LIVE_APPROVED` gate; no live transaction has been tested.

## Backups

Caddy's container health probe checks its loopback-only [administration endpoint](https://caddyserver.com/docs/api); port2019 is not published. This avoids assuming that a real domain's TLS certificate also covers localhost. Django has its own database/Redis readiness probe. The separate HTTPS smoke check verifies public routing; run it against the configured domain during deployment.

Backups contain a PostgreSQL custom dump, captured private media and a checksum manifest. Database totals and `pg_dump` use the same exported transaction snapshot. GPG encrypts the archive with AES256. Keep the passphrase file separate from both backups and source control.

For local validation:

```bash
bash scripts/recovery-test.sh
```

The script uses a private test key in the isolated Linux runtime, adds a synthetic private-file fixture, creates an encrypted backup and restores into a newly named isolated database. It checks database totals and every captured media hash, then removes only its passing restore database. Evidence is written to `.runtime/restore-evidence.json`.

The container CI recovery passed with 301 orders, 901 lines, 80 SKUs, 233 settlement events and one private-file fixture. The [full-fixture local recovery](evidence/restore.json) passed in **5.45 seconds** with **25,005 orders, 75,005 lines, 2,000 SKUs and four private files**. Settlement events and totals were also restored and reconciled. These checks do not establish off-server delivery or a production recovery SLA; their scope and counts are recorded in [VALIDATION.md](VALIDATION.md).

For the server, set `BACKUP_KEY_FILE` to a protected host passphrase file and `BACKUP_DIR` to the selected off-server mounted destination in the deployment environment. The destination must be writable by the backup container. The maintenance container joins the private database network and reads the private-media volume without publishing a database port.

```bash
bash scripts/backup-compose.sh
docker compose --env-file .env.production --profile maintenance run --rm backup \
  scripts/verify_restore.py /backups/PRODUCTSTAT_BACKUP_NAME.tar.gpg
```

Verification creates a new `productstat_restore_*` database, never restores over the source database, and compares the manifest's checks with the restored records. Failed verification retains the isolated database for inspection; passing verification removes it unless `--keep` is requested. Private files are verified in an isolated temporary directory; this command is a recovery check, not an automatic cutover of the live media volume.

The draft systemd service/timer targets a checkout at `/srv/productstat` with a Docker-capable service account. Verify a manual run, destination permissions and the installed timer before relying on its daily schedule. **RPO 24 hours and RTO four hours are selected targets**, not demonstrated production guarantees. Protect the key independently and test recovery from the actual off-server destination.

## Failures and maintenance

The protected `GET /api/v1/staff/operations-health/` endpoint gives administrators/operators uncached, redacted attention counts and up to 20 contributing references per category. It flags confirmed/preparing COD orders at least 48 hours old without cancelling them, failed imports, outbox work exhausted at eight attempts, and captured payment exceptions not covered by confirmed refunds. A worker crash on its eighth attempt is flagged after its five-minute lease expires. Analyst/customer accounts cannot access the endpoint; responses contain no customer names, contacts, addresses, file names or raw exception messages.

For local or container monitoring, run:

```bash
python backend/manage.py operations_check
docker compose --env-file .env.production exec -T backend python manage.py operations_check
```

The command writes JSON and exits **0** for clear checks, **1** for attention and **2** when database checks cannot complete. It sends no email or message. `deploy/productstat-operations.service` and `.timer` provide a five-minute host check after the configured Compose stack is running. Install them for the chosen Docker-capable service account and connect nonzero exit status/journal output to the deployment's alert receiver. No external alert destination has been configured or tested.

Rate-limit state is shared across application workers in Redis DB2 with a separate throttle namespace; reporting cache uses DB1 and Celery DB0. Pytest isolates throttle histories in a separate per-test memory cache. These are application request limits, not a substitute for deployment-level ingress controls.

- An unavailable gateway is shown as unavailable; do not manually label its order paid.
- Reservation cleanup releases unpaid expired stock; late captures become reconciliation/refund exceptions.
- COD collection and courier settlement are separate. Each settlement increment has its own immutable event, date and reference. Retrying the same reference/amount is safe; changing its amount is rejected. The payment's cumulative balance is not a date-filtered cash activity measure.
- Settlement migration recovers historical increments only when complete audits reconcile. Otherwise a marked legacy aggregate retains its observed timestamp; missing earlier transfer dates cannot be reconstructed from that snapshot. Reconcile legacy exceptions against source bank/courier records.
- Pending/failed outbox events remain in PostgreSQL. Restore Redis/worker/beat, inspect retry state and reconcile external email/payment evidence before manual retries.
- Import commits are atomic. Review the row errors, source IDs and batch report rather than editing totals directly.
- Historical source dates may be unknown; inspect coverage before interpreting a period's totals. An administrator-reviewed correction creates a current revision linked to the preserved original. It does not rewrite old settlement events or adjust live inventory. Retain the review reason and prior-revision evidence.
- A failed delivery is not an accepted customer return. Record physical receipt and inspection before changing sellable stock.
- Confirm a refund only with a real external reference. The confirmation endpoint does not transfer money.
- Before a release, preserve an encrypted backup, review migrations, deploy versioned images, verify readiness and smoke-test checkout. For incompatible migrations, recover the previous application and database together from the verified backup instead of attempting an unreviewed reverse migration.
- Monitor readiness, request latency, exhausted outbox retries, unreconciled payment exceptions, backup success and destination capacity. Direct maintenance writes affecting reports must append an audit event so committed-write cache invalidation remains reliable.
