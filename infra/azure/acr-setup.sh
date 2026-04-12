#!/usr/bin/env bash
#
# Create Azure Container Registry for Mission Control.
#
# Idempotent: safe to run multiple times. Creates the registry only
# if it does not already exist; always ensures admin access is enabled
# so CI pipelines can push with basic auth.

set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-mission-control}"
LOCATION="${LOCATION:-eastus}"
ACR_NAME="${ACR_NAME:-missioncontrolacr}"
ACR_SKU="${ACR_SKU:-Basic}"

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

ensure_provider() {
  local state
  state=$(az provider show --namespace Microsoft.ContainerRegistry --query registrationState -o tsv 2>/dev/null || echo "NotRegistered")
  if [[ "$state" != "Registered" ]]; then
    echo "Registering Microsoft.ContainerRegistry provider..."
    az provider register --namespace Microsoft.ContainerRegistry --wait
  fi
}

ensure_resource_group() {
  if ! az group show --name "$RESOURCE_GROUP" >/dev/null 2>&1; then
    echo "Creating resource group $RESOURCE_GROUP in $LOCATION..."
    az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none
  fi
}

ensure_acr() {
  if az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
    echo "ACR $ACR_NAME already exists — skipping creation"
  else
    echo "Creating ACR $ACR_NAME ($ACR_SKU) in $LOCATION..."
    az acr create \
      --resource-group "$RESOURCE_GROUP" \
      --name "$ACR_NAME" \
      --sku "$ACR_SKU" \
      --location "$LOCATION" \
      --output none
  fi

  echo "Enabling admin access on $ACR_NAME..."
  az acr update --name "$ACR_NAME" --admin-enabled true --output none
}

main() {
  require_az
  ensure_provider
  ensure_resource_group
  ensure_acr

  local login_server
  login_server=$(az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" --query loginServer -o tsv)
  echo ""
  echo "ACR ready."
  echo "  name:         $ACR_NAME"
  echo "  login server: $login_server"
  echo "  push with:    az acr login --name $ACR_NAME"
}

main "$@"
