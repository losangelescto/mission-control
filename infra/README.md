# Infrastructure

Setup scripts for Mission Control on Azure. Each script is idempotent —
safe to re-run after partial failures or config drift.

## Layout

```
infra/
├── azure/
│   ├── acr-setup.sh             # Azure Container Registry
│   ├── keyvault-setup.sh        # Key Vault + managed identity
│   ├── container-apps-setup.sh  # Production Container Apps environment
│   └── staging-setup.sh         # Staging environment (shares ACR/KV)
└── postgres/
    └── init.sql                 # Local Postgres init (docker-compose)
```

## Prerequisites

- Azure CLI 2.50 or later
- `containerapp` extension: installed automatically by the scripts that need it
- Signed in: `az login`
- Subscription set: `az account set --subscription <id>`
- Role: **Owner** on the target resource group (or User Access Administrator
  for the role assignments + Contributor for the resources)

## Order of Execution

Run these once, top to bottom. After the first run they can be re-executed
any time to reconcile drift.

```bash
cd infra/azure

# 1. Container registry — images get pushed here by CI
./acr-setup.sh

# 2. Key Vault + shared managed identity used by all container apps
./keyvault-setup.sh

# 3. Production Container Apps environment + mc-api + mc-web
./container-apps-setup.sh

# 4. Staging Container Apps environment + mc-api-staging + mc-web-staging
./staging-setup.sh
```

## Configuration

Every script reads its variables from the environment first, with sane
defaults. To override any value, export it before running:

```bash
RESOURCE_GROUP=mission-control-dev \
LOCATION=westus2 \
ACR_NAME=mcdevacr \
./acr-setup.sh
```

Common variables:

| Variable          | Default                  | Used by         |
|-------------------|--------------------------|-----------------|
| `RESOURCE_GROUP`  | `mission-control`        | all             |
| `LOCATION`        | `eastus`                 | all             |
| `ACR_NAME`        | `missioncontrolacr`      | acr, container apps, staging |
| `ACR_SKU`         | `Basic`                  | acr             |
| `KEYVAULT_NAME`   | `mc-keyvault`            | keyvault, container apps, staging |
| `IDENTITY_NAME`   | `mc-container-identity`  | keyvault, container apps, staging |
| `ENVIRONMENT_NAME`| `mc-environment`         | container apps  |
| `API_APP_NAME`    | `mc-api`                 | container apps  |
| `WEB_APP_NAME`    | `mc-web`                 | container apps  |
| `API_IMAGE_TAG`   | `latest`                 | container apps  |
| `WEB_IMAGE_TAG`   | `latest`                 | container apps  |
| `STAGING_ENVIRONMENT_NAME` | `mc-environment-staging` | staging |
| `STAGING_API_APP_NAME` | `mc-api-staging`    | staging         |
| `STAGING_WEB_APP_NAME` | `mc-web-staging`    | staging         |

## Verification

After each script, confirm the resource is healthy:

```bash
# ACR
az acr show --name missioncontrolacr --query "{name:name, login:loginServer, sku:sku.name}" -o table

# Key Vault + identity
az keyvault show --name mc-keyvault --query "{name:name, uri:properties.vaultUri}" -o table
az identity show --name mc-container-identity -g mission-control --query "{name:name, client:clientId}" -o table
az keyvault secret list --vault-name mc-keyvault --query "[].name" -o tsv

# Container Apps (prod)
az containerapp env show --name mc-environment -g mission-control --query "{name:name, state:properties.provisioningState}" -o table
az containerapp show --name mc-api -g mission-control --query "{name:name, fqdn:properties.configuration.ingress.fqdn}" -o table
az containerapp show --name mc-web -g mission-control --query "{name:name, fqdn:properties.configuration.ingress.fqdn}" -o table

# Container Apps (staging)
az containerapp show --name mc-api-staging -g mission-control --query "properties.configuration.ingress.fqdn" -o tsv
az containerapp show --name mc-web-staging -g mission-control --query "properties.configuration.ingress.fqdn" -o tsv

# Smoke test
curl -s "https://$(az containerapp show --name mc-api -g mission-control --query properties.configuration.ingress.fqdn -o tsv)/health"
```

## Updating Images

`container-apps-setup.sh` and `staging-setup.sh` update existing apps in
place, so re-running them after a new image push is how you deploy:

```bash
API_IMAGE_TAG=$(git rev-parse --short HEAD) ./container-apps-setup.sh
```

CI should push a tagged image to ACR first, then invoke the setup script
with that tag.

## Populating Secrets

All scripts seed Key Vault with `PLACEHOLDER_CHANGE_ME`. Real values are
written manually or by a secret-provisioning pipeline:

```bash
az keyvault secret set --vault-name mc-keyvault --name DATABASE-URL       --value "<real connection string>"
az keyvault secret set --vault-name mc-keyvault --name LLM-API-KEY        --value "<real api key>"
az keyvault secret set --vault-name mc-keyvault --name DATABASE-URL-STAGING --value "<staging connection string>"
az keyvault secret set --vault-name mc-keyvault --name LLM-API-KEY-STAGING  --value "<staging api key>"
```

Container apps pick up new secret versions on the next revision.

## Tear Down

Scripts do not delete resources. Use the CLI directly, from least to most
destructive:

```bash
# Remove only the apps (keeps environment, ACR, KV)
az containerapp delete -g mission-control -n mc-api       --yes
az containerapp delete -g mission-control -n mc-web       --yes
az containerapp delete -g mission-control -n mc-api-staging --yes
az containerapp delete -g mission-control -n mc-web-staging --yes

# Remove Container Apps environments
az containerapp env delete -g mission-control -n mc-environment         --yes
az containerapp env delete -g mission-control -n mc-environment-staging --yes

# Remove registry (destructive — deletes all pushed images)
az acr delete -n missioncontrolacr --yes

# Remove Key Vault (soft-deleted for 90 days; use --purge to fully remove)
az keyvault delete -n mc-keyvault
az keyvault purge   -n mc-keyvault

# Nuke the whole resource group
az group delete -n mission-control --yes --no-wait
```
