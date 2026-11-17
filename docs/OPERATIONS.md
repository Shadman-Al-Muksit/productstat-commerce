# Operations and recovery

## Local runtime

`scripts/env.sh` loads the ignored local `.env` and selects the isolated Linux dependencies. PostgreSQL17 uses port55433; Redis uses56379; Django8001; Next3000. These do not reuse the sibling Campus ERP ports.

Use `bash scripts/dev.sh` to run the API, interface, worker and scheduler. Application processes stop with Ctrl+C; database persistence is retained. Never remove the runtime cluster to fix a migration or schema error.

## Server deployment

Use an Ubuntu host with Docker Engine and the Compose plugin. From a private clone:

1. Copy `.env.production.example` to `.env.production`, replace all secret/domain placeholders and set company/demo flags correctly. Keep the file out of source control.
2. Point DNS at the host and permit ports80/443. Database and Redis have no host-published ports.
3. Run `docker compose --env-file .env.production config --quiet` and build the three images in CI.
4. Run `docker compose --env-file .env.production up -d --build`.
5. Create private staff credentials. For a synthetic demo, invoke `seed_demo` with separate strong `DEMO_PASSWORD` and `DEMO_VIEWER_PASSWORD`; expose only the analyst account publicly.
6. Check readiness, application logs, failed import/outbox states and a controlled end-to-end transaction. Confirm company shipping/tax/return settings before a real COD pilot.

Caddy terminates HTTPS. Django validates production secrets and hosts and sets secure session/CSRF cookies. The internal health endpoint avoids HTTPS redirects and probes database/Redis without returning credentials or exception details.

No successful container build or hosted deployment should be claimed until those jobs have actually run on a Docker-capable host.

## Backups

The backup contains a PostgreSQL custom dump plus private media and a checksum manifest. Database checksums/totals are collected in the same exported transaction snapshot as `pg_dump`. GPG uses AES256 symmetric encryption. Keep the key separate from the backups and repository.

For local validation:

```bash
bash scripts/recovery-test.sh
```

This creates a private test key in the isolated Linux runtime, a synthetic private-file fixture, an encrypted backup and an isolated restored database. It verifies stored totals and every restored media checksum, then removes only that newly created restore database. Results go to `.runtime/restore-evidence.json`.

For a server, set `BACKUP_KEY_FILE` to a protected host passphrase file and `BACKUP_DIR` to an off-server mounted destination in the deployment environment. Ensure the destination is writable by the backup container and monitored for available space. The backup container can reach the private database network without exposing a database port.

```bash
bash scripts/backup-compose.sh
docker compose --env-file .env.production --profile maintenance run --rm backup \
  scripts/verify_restore.py /backups/PRODUCTSTAT_BACKUP_NAME.tar.gpg
```

The draft systemd unit/timer can be installed on the target server with the repository at `/srv/productstat` and the Docker-capable service account configured. Verify one manual run and the timer before relying on a daily schedule. The selected RPO is24hours and RTO4hours; off-server operation must be demonstrated separately from the local restore.

## Failures and maintenance

- An unavailable gateway is shown as unavailable; do not manually label its order paid.
- Reservation cleanup releases unpaid expired stock; late captures become reconciliation exceptions.
- Pending/failed outbox events remain in PostgreSQL. Restore Redis/worker/beat, inspect retry state and reconcile external email/payment evidence before manual retries.
- Import commits are atomic. Review the row errors, source IDs and batch report rather than editing totals directly.
- A failed delivery is not an accepted customer return. Record physical receipt and inspection before changing sellable stock.
- Confirm a refund only with a real external reference. The confirmation endpoint does not transfer money.
- Before a release, preserve an encrypted backup, review migrations, deploy versioned images, verify readiness and smoke-test checkout. For incompatible migrations, recover the previous application and database together from the verified backup instead of attempting an unreviewed reverse migration.
- Logs carry request IDs and omit query strings, customer payloads and secrets. Monitor readiness failures, request latency, exhausted outbox retries and unreconciled payment exceptions.
