#!/usr/bin/env bash
#
# Create (or update) the production Container Apps environment and the
# API + Web container apps for Mission Control.
#
# Prerequisites (run in this order):
#   1. acr-setup.sh       — creates ACR and login server
#   2. keyvault-setup.sh  — creates Key Vault, identity, seeds secrets
#   3. This script
#
# The two apps share the same user-assigned managed identity so they can
# pull from ACR and read secrets from Key Vault without passwords.

set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-mission-control}"
LOCATION="${LOCATION:-eastus}"
ENVIRONMENT_NAME="${ENVIRONMENT_NAME:-mc-environment}"

ACR_NAME="${ACR_NAME:-missioncontrolacr}"
KEYVAULT_NAME="${KEYVAULT_NAME:-mc-keyvault}"
IDENTITY_NAME="${IDENTITY_NAME:-mc-container-identity}"

API_APP_NAME="${API_APP_NAME:-mc-api}"
WEB_APP_NAME="${WEB_APP_NAME:-mc-web}"
API_IMAGE_TAG="${API_IMAGE_TAG:-latest}"
WEB_IMAGE_TAG="${WEB_IMAGE_TAG:-latest}"

API_CPU="${API_CPU:-0.5}"
API_MEMORY="${API_MEMORY:-1.0Gi}"
API_MIN_REPLICAS="${API_MIN_REPLICAS:-1}"
API_MAX_REPLICAS="${API_MAX_REPLICAS:-3}"

WEB_CPU="${WEB_CPU:-0.5}"
WEB_MEMORY="${WEB_MEMORY:-1.0Gi}"
WEB_MIN_REPLICAS="${WEB_MIN_REPLICAS:-1}"
WEB_MAX_REPLICAS="${WEB_MAX_REPLICAS:-2}"

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
    echo "Installing containerapp extension..."
    az extension add --name containerapp --upgrade --output none
  fi
}

ensure_providers() {
  for ns in Microsoft.App Microsoft.OperationalInsights; do
    local state
    state=$(az provider show --namespace "$ns" --query registrationState -o tsv 2>/dev/null || echo "NotRegistered")
    if [[ "$state" != "Registered" ]]; then
      echo "Registering $ns provider..."
      az provider register --namespace "$ns" --wait
    fi
  done
}

ensure_environment() {
  if az containerapp env show --name "$ENVIRONMENT_NAME" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
    echo "Container Apps environment $ENVIRONMENT_NAME already exists"
  else
    echo "Creating Container Apps environment $ENVIRONMENT_NAME..."
    az containerapp env create \
      --name "$ENVIRONMENT_NAME" \
      --resource-group "$RESOURCE_GROUP" \
      --location "$LOCATION" \
      --output none
  fi
}

grant_acr_pull_to_identity() {
  local acr_id principal_id
  acr_id=$(az acr show --name "$ACR_NAME" --query id -o tsv)
  principal_id=$(az identity show --name "$IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" --query principalId -o tsv)

  echo "Granting AcrPull to managed identity..."
  az role assignment create \
    --assignee-object-id "$principal_id" \
    --assignee-principal-type ServicePrincipal \
    --role AcrPull \
    --scope "$acr_id" \
    --output none 2>/dev/null || true
}

# Inject liveness and readiness HTTP probes into an existing container app.
# Container Apps exposes probes through the full template spec, not CLI flags,
# so we read the current definition as JSON, add the probes block on every
# container, and re-apply. Idempotent — safe to run on an app that already
# has probes configured.
# Usage: configure_probes <app_name> <port>
configure_probes() {
  local app_name="$1"
  local port="$2"
  local tmp_spec
  tmp_spec=$(mktemp)
  # shellcheck disable=SC2064
  trap "rm -f $tmp_spec" RETURN

  az containerapp show \
    --name "$app_name" \
    --resource-group "$RESOURCE_GROUP" \
    --output json \
    | python3 - "$port" > "$tmp_spec" <<'PY'
import json, sys
port = int(sys.argv[1])
spec = json.load(sys.stdin)
probes = [
    {
        "type": "Liveness",
        "httpGet": {"path": "/health", "port": port, "scheme": "HTTP"},
        "periodSeconds": 30,
        "timeoutSeconds": 5,
        "failureThreshold": 3,
        "initialDelaySeconds": 10,
    },
    {
        "type": "Readiness",
        "httpGet": {"path": "/ready", "port": port, "scheme": "HTTP"},
        "periodSeconds": 10,
        "timeoutSeconds": 5,
        "failureThreshold": 5,
        "initialDelaySeconds": 5,
    },
]
for container in spec["properties"]["template"]["containers"]:
    container["probes"] = probes
# Strip read-only / system fields that --yaml rejects.
for key in ("id", "name", "type", "systemData"):
    spec.pop(key, None)
json.dump(spec, sys.stdout)
PY

  echo "Applying probes to $app_name..."
  az containerapp update \
    --name "$app_name" \
    --resource-group "$RESOURCE_GROUP" \
    --yaml "$tmp_spec" \
    --output none
}

# Usage: deploy_app <app_name> <image_repo> <port> <cpu> <memory> <min> <max>
deploy_app() {
  local app_name="$1"
  local image_repo="$2"
  local port="$3"
  local cpu="$4"
  local memory="$5"
  local min_replicas="$6"
  local max_replicas="$7"

  local identity_id acr_login kv_uri
  identity_id=$(az identity show --name "$IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" --query id -o tsv)
  acr_login=$(az acr show --name "$ACR_NAME" --query loginServer -o tsv)
  kv_uri=$(az keyvault show --name "$KEYVAULT_NAME" --resource-group "$RESOURCE_GROUP" --query properties.vaultUri -o tsv)
  kv_uri="${kv_uri%/}"

  local full_image="$acr_login/$image_repo"

  if az containerapp show --name "$app_name" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
    echo "Updating $app_name to image $full_image..."
    az containerapp update \
      --name "$app_name" \
      --resource-group "$RESOURCE_GROUP" \
      --image "$full_image" \
      --cpu "$cpu" \
      --memory "$memory" \
      --min-replicas "$min_replicas" \
      --max-replicas "$max_replicas" \
      --output none
    configure_probes "$app_name" "$port"
    return
  fi

  echo "Creating $app_name..."
  az containerapp create \
    --name "$app_name" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENVIRONMENT_NAME" \
    --image "$full_image" \
    --user-assigned "$identity_id" \
    --registry-server "$acr_login" \
    --registry-identity "$identity_id" \
    --target-port "$port" \
    --ingress external \
    --min-replicas "$min_replicas" \
    --max-replicas "$max_replicas" \
    --cpu "$cpu" \
    --memory "$memory" \
    --secrets \
      "database-url=keyvaultref:${kv_uri}/secrets/DATABASE-URL,identityref:${identity_id}" \
      "llm-api-key=keyvaultref:${kv_uri}/secrets/LLM-API-KEY,identityref:${identity_id}" \
    --env-vars \
      "DATABASE_URL=secretref:database-url" \
      "LLM_API_KEY=secretref:llm-api-key" \
    --output none
  configure_probes "$app_name" "$port"
}

print_fqdn() {
  local app_name="$1"
  local fqdn
  fqdn=$(az containerapp show --name "$app_name" --resource-group "$RESOURCE_GROUP" --query properties.configuration.ingress.fqdn -o tsv)
  echo "  $app_name: https://$fqdn"
}

main() {
  require_az
  ensure_providers
  ensure_environment
  grant_acr_pull_to_identity

  deploy_app "$API_APP_NAME" "mission-control-api:$API_IMAGE_TAG" 8000 \
    "$API_CPU" "$API_MEMORY" "$API_MIN_REPLICAS" "$API_MAX_REPLICAS"

  deploy_app "$WEB_APP_NAME" "mission-control-web:$WEB_IMAGE_TAG" 3000 \
    "$WEB_CPU" "$WEB_MEMORY" "$WEB_MIN_REPLICAS" "$WEB_MAX_REPLICAS"

  echo ""
  echo "Container apps ready."
  print_fqdn "$API_APP_NAME"
  print_fqdn "$WEB_APP_NAME"
}

main "$@"
