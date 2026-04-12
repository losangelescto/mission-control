#!/usr/bin/env bash
#
# Configure managed backups for the Mission Control PostgreSQL Flexible
# Server: 14-day retention with geo-redundancy.
#
# Idempotent — safe to re-run. Skips servers that already have the
# requested configuration.

set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-mission-control}"
POSTGRES_SERVER="${POSTGRES_SERVER:-mc-postgres}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
GEO_REDUNDANT_BACKUP="${GEO_REDUNDANT_BACKUP:-Enabled}"

require_az() {
  if ! command -v az >/dev/null 2>&1; then
    echo "ERROR: az CLI not found on PATH" >&2
    exit 1
  fi
  if ! az account show >/dev/null 2>&1; then
    echo "ERROR: not logged in. Run 'az login' first." >&2
    exit 1
  fi
}

ensure_server_exists() {
  if ! az postgres flexible-server show \
    --name "$POSTGRES_SERVER" \
    --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
    echo "ERROR: PostgreSQL server $POSTGRES_SERVER not found in $RESOURCE_GROUP" >&2
    echo "Provision the server first, then re-run this script." >&2
    exit 1
  fi
}

configure_retention() {
  local current_retention current_geo
  current_retention=$(az postgres flexible-server show \
    --name "$POSTGRES_SERVER" \
    --resource-group "$RESOURCE_GROUP" \
    --query "backup.backupRetentionDays" -o tsv)
  current_geo=$(az postgres flexible-server show \
    --name "$POSTGRES_SERVER" \
    --resource-group "$RESOURCE_GROUP" \
    --query "backup.geoRedundantBackup" -o tsv)

  if [[ "$current_retention" == "$BACKUP_RETENTION_DAYS" ]]; then
    echo "Retention already set to $BACKUP_RETENTION_DAYS days — skipping"
  else
    echo "Updating backup retention to $BACKUP_RETENTION_DAYS days..."
    az postgres flexible-server update \
      --name "$POSTGRES_SERVER" \
      --resource-group "$RESOURCE_GROUP" \
      --backup-retention "$BACKUP_RETENTION_DAYS" \
      --output none
  fi

  # Geo-redundant backup is only configurable at server creation time for
  # Flexible Server; it cannot be changed on an existing server. If it
  # does not already match, flag it clearly — the operator must provision
  # a new server with --geo-redundant-backup Enabled and migrate data.
  if [[ "$current_geo" != "$GEO_REDUNDANT_BACKUP" ]]; then
    echo ""
    echo "WARNING: geo-redundant backup is '$current_geo' on $POSTGRES_SERVER;"
    echo "         the desired state is '$GEO_REDUNDANT_BACKUP'."
    echo "         This setting is immutable post-creation. To enable geo-"
    echo "         redundancy, provision a new Flexible Server with"
    echo "         '--geo-redundant-backup Enabled' and restore the database"
    echo "         into it from a point-in-time backup."
    echo ""
  fi
}

print_status() {
  echo ""
  echo "Backup configuration:"
  az postgres flexible-server show \
    --name "$POSTGRES_SERVER" \
    --resource-group "$RESOURCE_GROUP" \
    --query "{server:name, retentionDays:backup.backupRetentionDays, geoRedundant:backup.geoRedundantBackup, earliestRestore:backup.earliestRestoreDate}" \
    --output table
}

print_restore_instructions() {
  cat <<EOF

To restore to a point in time, run:

  az postgres flexible-server restore \\
    --resource-group $RESOURCE_GROUP \\
    --name ${POSTGRES_SERVER}-restored-\$(date +%Y%m%d%H%M) \\
    --source-server $POSTGRES_SERVER \\
    --restore-time <ISO-8601 timestamp, e.g. 2026-04-12T19:30:00Z>

The earliest restore point is shown above. Point-in-time restore creates
a new server; the source is left untouched. After verifying the restored
server, swap connection strings in Key Vault.

For geo-restore to a paired region, add:
  --zone <zone-number> --location <paired-region>
EOF
}

main() {
  require_az
  ensure_server_exists
  configure_retention
  print_status
  print_restore_instructions
}

main "$@"
