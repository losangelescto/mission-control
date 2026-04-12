#!/usr/bin/env bash
#
# Create Key Vault + user-assigned managed identity for Mission Control.
#
# - Key Vault uses RBAC authorization (modern pattern, replaces access policies).
# - A single user-assigned managed identity is shared by API and Web container
#   apps. It is granted "Key Vault Secrets User" at vault scope.
# - Seed secrets are created with placeholder values only if the secret does
#   not already exist; real values must be set out-of-band.

set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-mission-control}"
LOCATION="${LOCATION:-eastus}"
KEYVAULT_NAME="${KEYVAULT_NAME:-mc-keyvault}"
IDENTITY_NAME="${IDENTITY_NAME:-mc-container-identity}"

SECRET_NAMES=(
  "DATABASE-URL"
  "LLM-API-KEY"
)

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

ensure_providers() {
  for ns in Microsoft.KeyVault Microsoft.ManagedIdentity; do
    local state
    state=$(az provider show --namespace "$ns" --query registrationState -o tsv 2>/dev/null || echo "NotRegistered")
    if [[ "$state" != "Registered" ]]; then
      echo "Registering $ns provider..."
      az provider register --namespace "$ns" --wait
    fi
  done
}

ensure_keyvault() {
  if az keyvault show --name "$KEYVAULT_NAME" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
    echo "Key Vault $KEYVAULT_NAME already exists — skipping creation"
  else
    echo "Creating Key Vault $KEYVAULT_NAME..."
    az keyvault create \
      --name "$KEYVAULT_NAME" \
      --resource-group "$RESOURCE_GROUP" \
      --location "$LOCATION" \
      --enable-rbac-authorization true \
      --output none
  fi
}

seed_secrets() {
  local current_user_id
  current_user_id=$(az ad signed-in-user show --query id -o tsv 2>/dev/null || echo "")
  local kv_scope
  kv_scope=$(az keyvault show --name "$KEYVAULT_NAME" --resource-group "$RESOURCE_GROUP" --query id -o tsv)

  if [[ -n "$current_user_id" ]]; then
    # Grant current user permission to write seed secrets (idempotent).
    az role assignment create \
      --assignee-object-id "$current_user_id" \
      --assignee-principal-type User \
      --role "Key Vault Secrets Officer" \
      --scope "$kv_scope" \
      --output none 2>/dev/null || true
  fi

  for secret in "${SECRET_NAMES[@]}"; do
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

ensure_identity() {
  if az identity show --name "$IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
    echo "Managed identity $IDENTITY_NAME already exists"
  else
    echo "Creating managed identity $IDENTITY_NAME..."
    az identity create \
      --name "$IDENTITY_NAME" \
      --resource-group "$RESOURCE_GROUP" \
      --location "$LOCATION" \
      --output none
  fi
}

grant_kv_read_to_identity() {
  local principal_id kv_scope
  principal_id=$(az identity show --name "$IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" --query principalId -o tsv)
  kv_scope=$(az keyvault show --name "$KEYVAULT_NAME" --resource-group "$RESOURCE_GROUP" --query id -o tsv)

  echo "Granting 'Key Vault Secrets User' to managed identity..."
  az role assignment create \
    --assignee-object-id "$principal_id" \
    --assignee-principal-type ServicePrincipal \
    --role "Key Vault Secrets User" \
    --scope "$kv_scope" \
    --output none 2>/dev/null || true
}

main() {
  require_az
  ensure_providers
  ensure_keyvault
  seed_secrets
  ensure_identity
  grant_kv_read_to_identity

  local kv_uri identity_client_id
  kv_uri=$(az keyvault show --name "$KEYVAULT_NAME" --resource-group "$RESOURCE_GROUP" --query properties.vaultUri -o tsv)
  identity_client_id=$(az identity show --name "$IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" --query clientId -o tsv)

  echo ""
  echo "Key Vault and managed identity ready."
  echo "  vault uri:          $kv_uri"
  echo "  identity name:      $IDENTITY_NAME"
  echo "  identity client id: $identity_client_id"
}

main "$@"
