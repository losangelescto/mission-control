# GitHub Actions Secrets

Every value below is required for the deploy workflows to run. CI
(`ci.yml`) needs none of these — it only builds and tests.

**Never commit real values to the repo.** This file is a reference for
what to configure in GitHub, not a place to store the secrets.

## Repository-level secrets

Configure at `Settings → Secrets and variables → Actions → Repository
secrets`. These are read by every workflow run in this repo.

| Name                    | Used by                | Description |
|-------------------------|------------------------|-------------|
| `AZURE_CREDENTIALS`     | staging, production    | Service principal JSON for `azure/login@v2`. See format below. |
| `ACR_LOGIN_SERVER`      | staging, production    | Fully-qualified registry hostname, e.g. `missioncontrolacr.azurecr.io`. |
| `ACR_USERNAME`          | staging, production    | Registry username (from `az acr credential show`). |
| `ACR_PASSWORD`          | staging, production    | Registry password (from `az acr credential show`). |
| `AZURE_RESOURCE_GROUP`  | staging, production    | Resource group containing the Container Apps, e.g. `mission-control`. |
| `STAGING_API_URL`       | staging                | Full HTTPS URL of the staging API, used as Next.js build-arg and health check target. |
| `STAGING_WEB_URL`       | staging                | Full HTTPS URL of the staging web app, used as health check target. |
| `PROD_API_URL`          | production             | Full HTTPS URL of the production API. |
| `PROD_WEB_URL`          | production             | Full HTTPS URL of the production web app. |

## Environment-scoped secrets (optional)

If you want production secrets fully isolated from staging, create a
GitHub Environment named `production` and move `AZURE_CREDENTIALS`,
`ACR_PASSWORD`, `PROD_API_URL`, and `PROD_WEB_URL` into it.
`deploy-production.yml` already references `environment: production`,
which activates the environment's required-reviewer gate and its secrets.

## Creating `AZURE_CREDENTIALS`

Create a service principal scoped to the resource group and save the
output as a single JSON value:

```bash
az ad sp create-for-rbac \
  --name mc-github-deployer \
  --role Contributor \
  --scopes /subscriptions/<SUBSCRIPTION_ID>/resourceGroups/mission-control \
  --sdk-auth
```

The resulting JSON looks like:

```json
{
  "clientId": "...",
  "clientSecret": "...",
  "subscriptionId": "...",
  "tenantId": "...",
  "activeDirectoryEndpointUrl": "https://login.microsoftonline.com",
  "resourceManagerEndpointUrl": "https://management.azure.com/",
  "activeDirectoryGraphResourceId": "https://graph.windows.net/",
  "sqlManagementEndpointUrl": "https://management.core.windows.net:8443/",
  "galleryEndpointUrl": "https://gallery.azure.com/",
  "managementEndpointUrl": "https://management.core.windows.net/"
}
```

Paste the whole object (including braces) into the `AZURE_CREDENTIALS`
secret. Do not wrap it in quotes.

Grant the same service principal `AcrPush` on the registry and
`Contributor` on the Container Apps so the deploy workflows can push
images and update revisions:

```bash
SP_OBJECT_ID=$(az ad sp list --display-name mc-github-deployer --query "[0].id" -o tsv)
ACR_ID=$(az acr show --name missioncontrolacr --query id -o tsv)

az role assignment create \
  --assignee-object-id "$SP_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role AcrPush \
  --scope "$ACR_ID"
```

## Getting ACR push credentials

```bash
az acr credential show --name missioncontrolacr
```

Use `username` for `ACR_USERNAME` and either `passwords[0].value` or
`passwords[1].value` for `ACR_PASSWORD`. Rotate by regenerating the
opposite password, updating the secret, then regenerating the first.

## Smoke test the config

After setting secrets, trigger a manual run of `ci.yml` first — it does
not touch Azure and will surface any workflow-file mistakes without
pushing images. Only then push to `staging` to verify the deploy flow.
