#!/usr/bin/env bash
#
# Create a separate staging environment for Mission Control.
#
# Shares the ACR, Key Vault, and managed identity with production but
# provisions its own Container Apps environment and app instances, with
# lower resource limits. Staging secrets live at separate Key Vault names
# so they can diverge from production without code changes.
#
# Staging expects a separate PostgreSQL database (or schema). Provide the
# connection string out-of-band by setting the DATABASE-URL-STAGING secret
# in the shared Key Vault before running this script.

set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-mission-control}"
LOCATION="${LOCATION:-eastus}"

STAGING_ENVIRONMENT_NAME="${STAGING_ENVIRONMENT_NAME:-mc-environment-staging}"
STAGING_API_APP_NAME="${STAGING_API_APP_NAME:-mc-api-staging}"
STAGING_WEB_APP_NAME="${STAGING_WEB_APP_NAME:-mc-web-staging}"
API_IMAGE_TAG="${API_IMAGE_TAG:-staging}"
WEB_IMAGE_TAG="${WEB_IMAGE_TAG:-staging}"

ACR_NAME="${ACR_NAME:-missioncontrolacr}"
KEYVAULT_NAME="${KEYVAULT_NAME:-mc-keyvault}"
IDENTITY_NAME="${IDENTITY_NAME:-mc-container-identity}"

STAGING_CPU="${STAGING_CPU:-0.25}"
STAGING_MEMORY="${STAGING_MEMORY:-0.5Gi}"
STAGING_MIN_REPLICAS="${STAGING_MIN_REPLICAS:-1}"
STAGING_MAX_REPLICAS="${STAGING_MAX_REPLICAS:-2}"

STAGING_SECRET_DATABASE_URL="${STAGING_SECRET_DATABASE_URL:-DATABASE-URL-STAGING}"
STAGING_SECRET_LLM_KEY="${STAGING_SECRET_LLM_KEY:-LLM-API-KEY-STAGING}"

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
}

ensure_staging_secrets() {
  for secret in "$STAGING_SECRET_DATABASE_URL" "$STAGING_SECRET_LLM_KEY"; do
    if az keyvault secret show --vault-name "$KEYVAULT_NAME" --name "$secret" >/dev/null 2>&1; then
      echo "  secret $secret already present — skipping"
    else
      echo "  seeding placeholder for $secret"
      az keyvault secret set \
        --vault-name "$KEYVAULT_NAME" \
        --name "$secret" \
        --value "PLACEHOLDER_CHANGE_ME" \
        --output none
    fi
  done
}

ensure_environment() {
  if az containerapp env show --name "$STAGING_ENVIRONMENT_NAME" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
    echo "Staging environment $STAGING_ENVIRONMENT_NAME already exists"
  else
    echo "Creating staging environment $STAGING_ENVIRONMENT_NAME..."
    az containerapp env create \
      --name "$STAGING_ENVIRONMENT_NAME" \
      --resource-group "$RESOURCE_GROUP" \
      --location "$LOCATION" \
      --output none
  fi
}

# Usage: deploy_staging_app <app_name> <image_repo> <port>
deploy_staging_app() {
  local app_name="$1"
  local image_repo="$2"
  local port="$3"

  local identity_id acr_login kv_uri
  identity_id=$(az identity show --name "$IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" --query id -o tsv)
  acr_login=$(az acr show --name "$ACR_NAME" --query loginServer -o tsv)
  kv_uri=$(az keyvault show --name "$KEYVAULT_NAME" --resource-group "$RESOURCE_GROUP" --query properties.vaultUri -o tsv)
  kv_uri="${kv_uri%/}"

  local full_image="$acr_login/$image_repo"

  if az containerapp show --name "$app_name" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
    echo "Updating $app_name to $full_image..."
    az containerapp update \
      --name "$app_name" \
      --resource-group "$RESOURCE_GROUP" \
      --image "$full_image" \
      --cpu "$STAGING_CPU" \
      --memory "$STAGING_MEMORY" \
      --min-replicas "$STAGING_MIN_REPLICAS" \
      --max-replicas "$STAGING_MAX_REPLICAS" \
      --output none
    return
  fi

  echo "Creating $app_name..."
  az containerapp create \
    --name "$app_name" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$STAGING_ENVIRONMENT_NAME" \
    --image "$full_image" \
    --user-assigned "$identity_id" \
    --registry-server "$acr_login" \
    --registry-identity "$identity_id" \
    --target-port "$port" \
    --ingress external \
    --min-replicas "$STAGING_MIN_REPLICAS" \
    --max-replicas "$STAGING_MAX_REPLICAS" \
    --cpu "$STAGING_CPU" \
    --memory "$STAGING_MEMORY" \
    --secrets \
      "database-url=keyvaultref:${kv_uri}/secrets/${STAGING_SECRET_DATABASE_URL},identityref:${identity_id}" \
      "llm-api-key=keyvaultref:${kv_uri}/secrets/${STAGING_SECRET_LLM_KEY},identityref:${identity_id}" \
    --env-vars \
      "APP_ENV=staging" \
      "DATABASE_URL=secretref:database-url" \
      "LLM_API_KEY=secretref:llm-api-key" \
    --output none
}

print_fqdn() {
  local app_name="$1"
  local fqdn
  fqdn=$(az containerapp show --name "$app_name" --resource-group "$RESOURCE_GROUP" --query properties.configuration.ingress.fqdn -o tsv)
  echo "  $app_name: https://$fqdn"
}

main() {
  require_az
  ensure_staging_secrets
  ensure_environment

  deploy_staging_app "$STAGING_API_APP_NAME" "mission-control-api:$API_IMAGE_TAG" 8000
  deploy_staging_app "$STAGING_WEB_APP_NAME" "mission-control-web:$WEB_IMAGE_TAG" 3000

  echo ""
  echo "Staging environment ready."
  print_fqdn "$STAGING_API_APP_NAME"
  print_fqdn "$STAGING_WEB_APP_NAME"
  echo ""
  echo "Remember to populate these secrets with real values before use:"
  echo "  $STAGING_SECRET_DATABASE_URL"
  echo "  $STAGING_SECRET_LLM_KEY"
}

main "$@"
