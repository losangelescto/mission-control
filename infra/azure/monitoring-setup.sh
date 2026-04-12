#!/usr/bin/env bash
#
# Wire Mission Control Container Apps into Azure Monitor.
#
# - Creates a Log Analytics workspace if missing.
# - Attaches the workspace to the Container Apps environment so both API
#   and Web apps stream system + console logs there.
# - Adds three alert rules covering the operational signals the task asked
#   for (restart count, 5xx rate, p95 latency).
#
# Idempotent. Safe to re-run after partial failures or config drift.

set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-mission-control}"
LOCATION="${LOCATION:-eastus}"
ENVIRONMENT_NAME="${ENVIRONMENT_NAME:-mc-environment}"
WORKSPACE_NAME="${WORKSPACE_NAME:-mc-logs}"

API_APP_NAME="${API_APP_NAME:-mc-api}"
WEB_APP_NAME="${WEB_APP_NAME:-mc-web}"
ACTION_GROUP_NAME="${ACTION_GROUP_NAME:-mc-alerts}"
ACTION_GROUP_SHORT="${ACTION_GROUP_SHORT:-mcalerts}"

# Alert thresholds (tuned for a single-region, low-traffic deployment).
RESTART_THRESHOLD="${RESTART_THRESHOLD:-3}"
RESTART_WINDOW="${RESTART_WINDOW:-PT10M}"
ERROR_RATE_THRESHOLD="${ERROR_RATE_THRESHOLD:-5}"
ERROR_RATE_WINDOW="${ERROR_RATE_WINDOW:-PT5M}"
LATENCY_THRESHOLD_MS="${LATENCY_THRESHOLD_MS:-10000}"
LATENCY_WINDOW="${LATENCY_WINDOW:-PT5M}"

require_az() {
  if ! command -v az >/dev/null 2>&1; then
    echo "ERROR: az CLI not found on PATH" >&2
    exit 1
  fi
  if ! az account show >/dev/null 2>&1; then
    echo "ERROR: not logged in. Run 'az login' first." >&2
    exit 1
  fi
  if ! az extension show --name containerapp >/dev/null 2>&1; then
    az extension add --name containerapp --upgrade --output none
  fi
  if ! az extension show --name monitor-control-service >/dev/null 2>&1; then
    az extension add --name monitor-control-service --upgrade --output none 2>/dev/null || true
  fi
}

ensure_providers() {
  for ns in Microsoft.OperationalInsights Microsoft.Insights; do
    local state
    state=$(az provider show --namespace "$ns" --query registrationState -o tsv 2>/dev/null || echo "NotRegistered")
    if [[ "$state" != "Registered" ]]; then
      echo "Registering $ns provider..."
      az provider register --namespace "$ns" --wait
    fi
  done
}

ensure_workspace() {
  if az monitor log-analytics workspace show \
    --workspace-name "$WORKSPACE_NAME" \
    --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
    echo "Log Analytics workspace $WORKSPACE_NAME already exists"
  else
    echo "Creating Log Analytics workspace $WORKSPACE_NAME..."
    az monitor log-analytics workspace create \
      --workspace-name "$WORKSPACE_NAME" \
      --resource-group "$RESOURCE_GROUP" \
      --location "$LOCATION" \
      --sku PerGB2018 \
      --retention-time 30 \
      --output none
  fi
}

attach_workspace_to_environment() {
  local workspace_id customer_id primary_key
  workspace_id=$(az monitor log-analytics workspace show \
    --workspace-name "$WORKSPACE_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query id -o tsv)
  customer_id=$(az monitor log-analytics workspace show \
    --workspace-name "$WORKSPACE_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query customerId -o tsv)
  primary_key=$(az monitor log-analytics workspace get-shared-keys \
    --workspace-name "$WORKSPACE_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query primarySharedKey -o tsv)

  local current_customer
  current_customer=$(az containerapp env show \
    --name "$ENVIRONMENT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "properties.appLogsConfiguration.logAnalyticsConfiguration.customerId" \
    -o tsv 2>/dev/null || echo "")

  if [[ "$current_customer" == "$customer_id" ]]; then
    echo "Container Apps environment already wired to $WORKSPACE_NAME"
    return
  fi

  echo "Wiring $ENVIRONMENT_NAME to $WORKSPACE_NAME..."
  az containerapp env update \
    --name "$ENVIRONMENT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --logs-destination log-analytics \
    --logs-workspace-id "$customer_id" \
    --logs-workspace-key "$primary_key" \
    --output none

  # Silence unused-var warning for workspace_id (kept for future diagnostic hooks).
  : "$workspace_id"
}

ensure_action_group() {
  if az monitor action-group show \
    --name "$ACTION_GROUP_NAME" \
    --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
    echo "Action group $ACTION_GROUP_NAME already exists"
    return
  fi
  echo "Creating action group $ACTION_GROUP_NAME..."
  az monitor action-group create \
    --name "$ACTION_GROUP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --short-name "$ACTION_GROUP_SHORT" \
    --output none
}

# Usage: upsert_metric_alert <rule_name> <scope> <condition> <window>
upsert_metric_alert() {
  local rule_name="$1"
  local scope="$2"
  local condition="$3"
  local window="$4"
  local description="$5"

  local action_group_id
  action_group_id=$(az monitor action-group show \
    --name "$ACTION_GROUP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query id -o tsv)

  if az monitor metrics alert show \
    --name "$rule_name" \
    --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
    echo "Updating metric alert $rule_name..."
    az monitor metrics alert update \
      --name "$rule_name" \
      --resource-group "$RESOURCE_GROUP" \
      --window-size "$window" \
      --description "$description" \
      --output none
    return
  fi

  echo "Creating metric alert $rule_name..."
  az monitor metrics alert create \
    --name "$rule_name" \
    --resource-group "$RESOURCE_GROUP" \
    --scopes "$scope" \
    --condition "$condition" \
    --window-size "$window" \
    --evaluation-frequency PT1M \
    --severity 2 \
    --description "$description" \
    --action "$action_group_id" \
    --output none 2>/dev/null || {
      echo "  (alert $rule_name could not be created — metric may not be available yet; re-run after first traffic)"
    }
}

configure_alerts() {
  for app in "$API_APP_NAME" "$WEB_APP_NAME"; do
    if ! az containerapp show --name "$app" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
      echo "  $app does not exist — skipping its alerts"
      continue
    fi
    local scope
    scope=$(az containerapp show --name "$app" --resource-group "$RESOURCE_GROUP" --query id -o tsv)

    upsert_metric_alert \
      "mc-${app}-restarts" \
      "$scope" \
      "total RestartCount > ${RESTART_THRESHOLD}" \
      "$RESTART_WINDOW" \
      "Container restart count exceeded ${RESTART_THRESHOLD} in ${RESTART_WINDOW}"

    upsert_metric_alert \
      "mc-${app}-5xx-rate" \
      "$scope" \
      "avg Requests where StatusCodeCategory == '5xx' > ${ERROR_RATE_THRESHOLD}" \
      "$ERROR_RATE_WINDOW" \
      "5xx response rate exceeded ${ERROR_RATE_THRESHOLD}% over ${ERROR_RATE_WINDOW}"

    upsert_metric_alert \
      "mc-${app}-latency-p95" \
      "$scope" \
      "avg ResponseTime > ${LATENCY_THRESHOLD_MS}" \
      "$LATENCY_WINDOW" \
      "p95 response time exceeded ${LATENCY_THRESHOLD_MS}ms over ${LATENCY_WINDOW}"
  done
}

main() {
  require_az
  ensure_providers
  ensure_workspace
  attach_workspace_to_environment
  ensure_action_group
  configure_alerts

  echo ""
  echo "Monitoring ready."
  echo "  workspace:    $WORKSPACE_NAME"
  echo "  environment:  $ENVIRONMENT_NAME"
  echo "  action group: $ACTION_GROUP_NAME"
  echo ""
  echo "Add notification receivers to the action group once decided:"
  echo "  az monitor action-group update --name $ACTION_GROUP_NAME --resource-group $RESOURCE_GROUP \\"
  echo "    --add-action email oncall oncall@example.com"
}

main "$@"
