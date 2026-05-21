#!/usr/bin/env bash
# Backup script for Telegram Message Migrator.
#
# Snapshots the SQLite database (consistent via VACUUM INTO) and the
# Telethon sessions directory, into a timestamped folder under
# $BACKUP_DIR (defaults to ./backups).
#
# Designed to run on the production VM. Safe to run while the app is
# live -- VACUUM INTO is atomic and sessions are read-only at rest
# from the host's perspective (Telethon holds them open via the
# container; the host can still read the file).
#
# Usage:
#   bash scripts/backup.sh                          # default path layout
#   BACKUP_DIR=/var/backups/tgmigrate bash scripts/backup.sh
#   RETENTION_DAYS=14 bash scripts/backup.sh        # prune > N days old
#
# Cron example (root crontab on VM, weekly Sunday 03:00):
#   0 3 * * 0 cd /home/bolin8017/telegram-message-migrator && \
#     BACKUP_DIR=/var/backups/tgmigrate RETENTION_DAYS=28 \
#     bash scripts/backup.sh >> /var/log/tgmigrate-backup.log 2>&1
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$REPO_ROOT/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-0}"  # 0 = no pruning

TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
DEST="$BACKUP_DIR/tgmigrate-$TIMESTAMP"
mkdir -p "$DEST"

echo "[backup] target: $DEST"

# 1. SQLite snapshot via VACUUM INTO (atomic; safe with live writes).
# The compose stack mounts /data inside the app container, which maps
# to a docker named volume. We use docker exec to run sqlite3 against
# the in-container path /data/data.db.
APP_CONTAINER="telegram-message-migrator-app-1"
if sudo docker ps --format '{{.Names}}' | grep -q "^$APP_CONTAINER$"; then
    echo "[backup] running VACUUM INTO via $APP_CONTAINER"
    sudo docker exec "$APP_CONTAINER" \
        python -c "import sqlite3, os; src='/data/data.db'; dst='/data/.backup-${TIMESTAMP}.db'; conn=sqlite3.connect(src); conn.execute(f\"VACUUM INTO '{dst}'\"); conn.close(); print('ok', dst)"
    # Copy the snapshot out of the volume via docker cp
    sudo docker cp "$APP_CONTAINER:/data/.backup-${TIMESTAMP}.db" "$DEST/data.db"
    sudo docker exec "$APP_CONTAINER" rm -f "/data/.backup-${TIMESTAMP}.db"
    sudo chown "$USER:$USER" "$DEST/data.db" 2>/dev/null || true
else
    echo "[backup] WARN: container $APP_CONTAINER not running; copying data.db directly (may not be crash-consistent)"
    DB_PATH="${DB_PATH:-$REPO_ROOT/data.db}"
    if [ -f "$DB_PATH" ]; then
        cp "$DB_PATH" "$DEST/data.db"
    else
        echo "[backup] WARN: $DB_PATH not found; skipping DB"
    fi
fi

# 2. Sessions directory snapshot (tar.gz from inside the container).
echo "[backup] tarring sessions/"
if sudo docker ps --format '{{.Names}}' | grep -q "^$APP_CONTAINER$"; then
    sudo docker exec "$APP_CONTAINER" tar -C /data -czf "/data/.sessions-${TIMESTAMP}.tar.gz" sessions 2>/dev/null \
        && sudo docker cp "$APP_CONTAINER:/data/.sessions-${TIMESTAMP}.tar.gz" "$DEST/sessions.tar.gz" \
        && sudo docker exec "$APP_CONTAINER" rm -f "/data/.sessions-${TIMESTAMP}.tar.gz" \
        || echo "[backup] WARN: sessions tar failed (directory may be empty)"
    sudo chown "$USER:$USER" "$DEST/sessions.tar.gz" 2>/dev/null || true
else
    SESS_DIR="${SESSION_DIR:-$REPO_ROOT/sessions}"
    if [ -d "$SESS_DIR" ]; then
        tar -czf "$DEST/sessions.tar.gz" -C "$(dirname "$SESS_DIR")" "$(basename "$SESS_DIR")"
    fi
fi

# 3. Manifest with sha256 sums for integrity-check on restore.
(
    cd "$DEST"
    sha256sum * > MANIFEST.sha256 2>/dev/null || true
    ls -la
) | tail -10

# 4. Retention pruning.
if [ "$RETENTION_DAYS" -gt 0 ]; then
    echo "[backup] pruning backups older than $RETENTION_DAYS days under $BACKUP_DIR"
    find "$BACKUP_DIR" -maxdepth 1 -type d -name 'tgmigrate-*' -mtime "+$RETENTION_DAYS" -print -exec rm -rf {} \;
fi

echo "[backup] done: $DEST"
