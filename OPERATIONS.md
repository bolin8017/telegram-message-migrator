# Operations Runbook

Operational reference for the hosted instance at <https://tgmigrate.com> and
self-hosted deployments using the same Docker Compose stack.

For first-time provisioning see [`scripts/gcp-bootstrap.md`](scripts/gcp-bootstrap.md).
For the security disclosure process see [`SECURITY.md`](SECURITY.md).

---

## Topology

```
client
  └─> Cloudflare proxy (orange cloud, "Full" TLS mode)
         └─> GCP e2-micro VM (us-west1-b, external IP)
                ├─> :80, :443  Caddy 2.x (tls internal, trusts CF edge IPs)
                └─> :8000     FastAPI (uvicorn, single worker)
                                ├─ SQLite at /data/data.db (encrypted creds/sessions in multi-user mode)
                                └─ Telethon .session files at /data/sessions/
```

The compose stack is checked out at `~/telegram-message-migrator` on the VM.
Containers are managed by Docker Compose with `restart: unless-stopped`, so the
VM coming back up after a reboot brings everything up automatically.

---

## Deploying a new version

CI publishes `ghcr.io/bolin8017/telegram-message-migrator:latest` on every push
to `main`. To roll forward on the VM:

```bash
gcloud compute ssh homelab --zone=us-west1-b
cd ~/telegram-message-migrator
git pull --ff-only origin main      # if any compose / Caddyfile changed
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

`pull_policy: always` in `docker-compose.yml` would also fetch on `up -d`, but
explicit `pull` is faster to reason about. The `up -d` recreates only the
containers whose image changed.

### Verifying after deploy

```bash
curl -sf https://tgmigrate.com/health     # expect {"status":"ok"}
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml ps   # both Up; app (healthy)
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=20 app | grep -i error || echo "no recent errors"
```

### Rolling back

The previous image is normally still in the local docker cache. If GHCR has a
`:sha-<commit>` tag for a known-good prior commit:

```bash
sudo docker pull ghcr.io/bolin8017/telegram-message-migrator:sha-<commit>
sudo docker tag ghcr.io/bolin8017/telegram-message-migrator:sha-<commit> \
                ghcr.io/bolin8017/telegram-message-migrator:latest
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

For schema-affecting changes, restore the DB from a backup before rolling
forward again.

---

## Restart / recreate

| Goal | Command |
|---|---|
| Restart app only | `sudo docker compose -f ... restart app` |
| Restart Caddy only | `sudo docker compose -f ... restart caddy` |
| Recreate stack (re-read compose + .env) | `sudo docker compose -f ... up -d --force-recreate` |
| Stop stack | `sudo docker compose -f ... down` |
| Stop and remove volumes (**destructive**) | `sudo docker compose -f ... down -v`  -- this wipes SQLite + sessions |

Docker auto-starts the stack on host boot via `restart: unless-stopped` plus
`docker.service`. No systemd unit needed.

---

## Logs

The app logs to stdout; Docker captures via the json-file driver with
size-rotation already configured in `docker-compose.prod.yml`
(10 MB per file, 3 files kept).

```bash
# Live tail
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f app
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f caddy

# Look for errors in the last 500 lines
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=500 app | grep -iE 'error|exception|traceback'

# Caddy access patterns (Caddy logs errors by default; for full access logs you'd
# add a 'log' directive in the Caddyfile -- not enabled, see "What's not here")
```

To switch the app to JSON-formatted logs (for shipping to a log aggregator),
set `LOG_FORMAT=json` in `.env` and restart. Default is text.

---

## Backups

`scripts/backup.sh` snapshots the database (via `VACUUM INTO`, crash-consistent
without blocking writers) and `sessions/` (tar.gz). Both come out of the
running container's `/data` volume via `docker exec` + `docker cp`.

### Manual backup

```bash
cd ~/telegram-message-migrator
BACKUP_DIR=/var/backups/tgmigrate bash scripts/backup.sh
ls -la /var/backups/tgmigrate/
```

### Scheduled backup (recommended)

Add to root crontab on the VM:

```cron
0 3 * * 0 cd /home/bolin8017/telegram-message-migrator && \
  BACKUP_DIR=/var/backups/tgmigrate RETENTION_DAYS=28 \
  bash scripts/backup.sh >> /var/log/tgmigrate-backup.log 2>&1
```

This runs Sunday 03:00 UTC, retains backups for 28 days.

### Restore

```bash
# Stop the app first
cd ~/telegram-message-migrator
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml stop app

# Verify the backup integrity
cd /var/backups/tgmigrate/tgmigrate-20260521-030000
sha256sum -c MANIFEST.sha256

# Restore DB into the volume
sudo docker run --rm -v telegram-message-migrator_app_data:/data \
  -v "$(pwd):/restore" \
  alpine sh -c 'cp /restore/data.db /data/data.db && chown 100:101 /data/data.db'

# Restore sessions/
sudo docker run --rm -v telegram-message-migrator_app_data:/data \
  -v "$(pwd):/restore" \
  alpine sh -c 'cd /data && rm -rf sessions && tar -xzf /restore/sessions.tar.gz && chown -R 100:101 sessions'

# Start back up
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
curl -sf https://tgmigrate.com/health
```

Volume name `telegram-message-migrator_app_data` is the compose-generated name
for the `app_data:` volume; verify with `sudo docker volume ls`.

---

## Common incidents

### App unhealthy / restart loop

```bash
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml ps      # confirm unhealthy
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=100 app
```

Most common causes:

- **CONFIG ERROR on startup** -- `SERVER_SECRET` < 32 chars, missing `TELEGRAM_API_ID`/`HASH` in single-user mode. Check `.env`.
- **CORS rejected** -- the SPA can't reach the API. Check `CORS_ORIGINS` matches the public URL.
- **DB locked** -- a previous `VACUUM INTO` left a stale lock. Restart the app container.
- **Image pulled but doesn't start** -- a new commit introduced a bug. Roll back per the "Rolling back" section above.

### Caddy serving 5xx / TLS handshake fails

```bash
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=100 caddy
```

- **Cert challenge failing** -- check `TLS_MODE`. Behind Cloudflare proxy it MUST be `tls internal`; on direct DNS leave it unset.
- **502 Bad Gateway** -- `app` is down or unhealthy. Check the app logs first.

### Disk filling up

```bash
df -h
sudo docker system df       # how much docker is using
sudo du -sh /var/lib/docker/* | sort -rh | head
sudo docker volume ls       # named volumes
sudo docker system prune -af    # purge unused images/containers (safe; keeps named volumes)
```

The compose `logging:` driver caps app logs at 30 MB total. The big growth
drivers are typically old container images that have piled up over deploys.

### CPU 100% / OOM

The prod overlay limits the app to 1 CPU and 512 MB. If you see container
restarts with exit 137 (SIGKILL), it's the memory limit. Raise via
`docker-compose.prod.yml` `deploy.resources.limits.memory` -- but investigate
the leak first (transfer pipelines holding large media in RAM should not
happen; we stream to disk).

### Rate-limit / flood-wait spikes

If multiple users hit FloodWait simultaneously, the global semaphore caps
concurrent jobs (`MAX_CONCURRENT_JOBS=10` by default). Lower in `.env` if you
need to back off harder, then `restart app`.

---

## GitHub-side ops

| Task | Where |
|---|---|
| View Dependabot alerts | <https://github.com/bolin8017/telegram-message-migrator/security/dependabot> |
| View Trivy / code scanning findings | <https://github.com/bolin8017/telegram-message-migrator/security/code-scanning> |
| Approve / merge Dependabot PRs | <https://github.com/bolin8017/telegram-message-migrator/pulls?q=author%3Aapp%2Fdependabot> |
| Watch CI on `main` | `gh run watch` after a push |
| Re-run a flaky CI job | `gh run rerun <run-id> --failed` |

---

## What's NOT here (and why)

Deliberate omissions to keep this runbook short:

- **Prometheus `/metrics` + Grafana** -- no observability backend yet; the `/health` endpoint and `docker compose logs` are the current source of truth.
- **Caddy access logs** -- not enabled by default; the json-file driver captures container stdout which is enough for this scale. Enable via a `log { output stdout }` directive inside the site block if needed.
- **Auto-deploy from CI** -- production rollout is one `gcloud ssh` + two commands. Deliberately not automated until traffic warrants it.
- **Multi-region failover** -- single GCP zone is fine for the hosted instance's volume; downtime during regional outages is acceptable.

If any of those start being missed in practice, file an issue and we'll add them.
