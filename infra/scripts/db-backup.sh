#!/usr/bin/env bash
#
# Manual PostgreSQL backup to Azure Blob Storage.
#
# Runs pg_dump against the configured database, uploads the compressed
# dump to a blob container, then prunes local and remote copies older
# than RETENTION_DAYS days (default 30).
#
# Intended to be triggered by hand, a cron job, or an Azure Automation
# runbook — it is fully self-contained given a DATABASE_URL and storage
# credentials.
#
# Required:
#   DATABASE_URL        postgres connection string
#   AZURE_STORAGE_ACCOUNT  blob storage account name
#
# Authentication to the storage account can be provided via any of:
#   AZURE_STORAGE_KEY
#   AZURE_STORAGE_SAS_TOKEN
#   or ambient AAD credentials (preferred — use managed identity)

set -euo pipefail

DATABASE_URL="${DATABASE_URL:?DATABASE_URL is required}"
AZURE_STORAGE_ACCOUNT="${AZURE_STORAGE_ACCOUNT:?AZURE_STORAGE_ACCOUNT is required}"
BACKUP_CONTAINER="${BACKUP_CONTAINER:-db-backups}"
BACKUP_DIR="${BACKUP_DIR:-/tmp/mc-db-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

require_commands() {
  for cmd in pg_dump az gzip; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      echo "ERROR: $cmd not found on PATH" >&2
      exit 1
    fi
  done
}

dump_database() {
  mkdir -p "$BACKUP_DIR"
  local timestamp filename
  timestamp=$(date -u +%Y%m%dT%H%M%SZ)
  filename="mission-control-${timestamp}.sql.gz"
  local path="${BACKUP_DIR}/${filename}"

  echo "Dumping database to $path..."
  pg_dump --no-owner --no-privileges --format=plain "$DATABASE_URL" | gzip -9 > "$path"
  echo "$path"
}

ensure_container() {
  az storage container create \
    --name "$BACKUP_CONTAINER" \
    --account-name "$AZURE_STORAGE_ACCOUNT" \
    --output none 2>/dev/null || true
}

upload_dump() {
  local path="$1"
  local name
  name=$(basename "$path")
  echo "Uploading $name to ${AZURE_STORAGE_ACCOUNT}/${BACKUP_CONTAINER}..."
  az storage blob upload \
    --account-name "$AZURE_STORAGE_ACCOUNT" \
    --container-name "$BACKUP_CONTAINER" \
    --file "$path" \
    --name "$name" \
    --overwrite false \
    --output none
}

prune_local_dumps() {
  find "$BACKUP_DIR" -type f -name 'mission-control-*.sql.gz' -mtime +"$RETENTION_DAYS" -delete 2>/dev/null || true
}

prune_remote_dumps() {
  local cutoff
  cutoff=$(date -u -d "${RETENTION_DAYS} days ago" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
           || date -u -v-"${RETENTION_DAYS}"d +%Y-%m-%dT%H:%M:%SZ)

  local blobs
  blobs=$(az storage blob list \
    --account-name "$AZURE_STORAGE_ACCOUNT" \
    --container-name "$BACKUP_CONTAINER" \
    --query "[?properties.creationTime<='${cutoff}'].name" \
    --output tsv 2>/dev/null || true)

  if [[ -z "$blobs" ]]; then
    return
  fi

  while IFS= read -r blob; do
    [[ -z "$blob" ]] && continue
    echo "Deleting old blob: $blob"
    az storage blob delete \
      --account-name "$AZURE_STORAGE_ACCOUNT" \
      --container-name "$BACKUP_CONTAINER" \
      --name "$blob" \
      --output none || true
  done <<<"$blobs"
}

main() {
  require_commands
  ensure_container
  local dump_path
  dump_path=$(dump_database)
  upload_dump "$dump_path"
  prune_local_dumps
  prune_remote_dumps
  echo "Backup complete: $(basename "$dump_path")"
}

main "$@"
