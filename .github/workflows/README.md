# GitHub Actions Workflows

This directory contains CI/CD workflows for the Estate Value Index project.

## 📋 Overview

| Workflow | Status | Trigger | Purpose |
|----------|--------|---------|---------|
| **ci.yml** | Enabled | Push, PR | Run tests and linting |
| **deploy.yml** | Manual | `workflow_dispatch` | Deploy web app to Cloud Run |
| **ml-pipeline.yml** | Manual | `workflow_dispatch` | Run retraining / Vertex AI pipeline |
| **ml-monitoring.yml** | Manual | `workflow_dispatch` | Run drift detection |

---

## 🔄 CI Workflow (Enabled)

**File:** `ci.yml`  
**Triggers:** Automatic on push to `main`, `develop`, `ml-production-time` or pull requests

### What it does:

1. **Python Tests & Linting**
   - Runs 126 tests across 9 test files
   - Tests: `src/estate_value_index/{ml,ingestion,pipelines}`
   - Checks code formatting (Black) and import sorting (isort)
   - Generates coverage report

2. **TypeScript Tests & Linting**
   - Runs Jest tests for Next.js web app
   - ESLint linting
   - TypeScript type checking

3. **Dockerfile Validation**
   - Builds web app Dockerfile (`./Dockerfile`)
   - Builds training container Dockerfile (`./vertex_ai/Dockerfile`)
   - Validates both build successfully

### Usage:

Automatically runs on every push and pull request. No manual action needed.

---

## 🚀 Deploy Web App (Disabled)

**File:** `deploy.yml`  
**Triggers:** Manual only (`workflow_dispatch`)

### What it does:

1. Builds web app Docker image
2. Pushes to Google Container Registry
3. Deploys to Cloud Run
4. Runs smoke test
5. Reports deployment URL

### Usage:

```bash
# Via GitHub UI:
Actions → Deploy Web App → Run workflow → Select environment

# Via GitHub CLI:
gh workflow run deploy.yml -f environment=staging
gh workflow run deploy.yml -f environment=production  # protected environment
```

### Parameters:

| Parameter | Options | Default | Description |
|-----------|---------|---------|-------------|
| `environment` | staging, production | staging | Deployment target; production should require environment protection |

---

## 🧠 ML Pipeline

**File:** `ml-pipeline.yml`
**Triggers:** Manual only (`workflow_dispatch`)

### What it does:

1. Sets up Python environment
2. Authenticates to Google Cloud (if Vertex AI mode)
3. Runs training job (Vertex AI or local)
4. Uploads model artifacts
5. Reports training metrics

### Usage:

```bash
# Quick Vertex AI training (no tuning)
gh workflow run ml-pipeline.yml -f environment=staging -f mode=vertex -f tune=false

# Production training (with tuning)
gh workflow run ml-pipeline.yml -f environment=production -f mode=vertex -f tune=true

# Local training (for testing)
gh workflow run ml-pipeline.yml -f environment=staging -f mode=local -f tune=false
```

### Parameters:

| Parameter | Options | Default | Description |
|-----------|---------|---------|-------------|
| `environment` | staging, production | staging | GitHub environment containing cloud vars/secrets |
| `mode` | retrain, full, vertex, local | retrain | Pipeline mode |
| `tune` | true, false | true | Enable hyperparameter tuning |
| `deploy` | true, false | false | Deploy to Cloud Run after training |

### Costs:

| Configuration | Duration | Estimated Cost |
|---------------|----------|----------------|
| Quick (no tuning) | ~10-15 min | ~$0.10 |
| Production (tuning) | ~25-30 min | ~$0.35 |
| Local | ~5-10 min | $0 |

---

## 🔐 Required Cloud Configuration

Cloud workflows use GitHub environments and Google Workload Identity Federation. Do not store long-lived GCP service-account JSON keys in repository secrets.

Create `staging` and/or `production` GitHub environments with these variables:

| Variable | Description | Required For |
|----------|-------------|--------------|
| `GCP_PROJECT_ID` | Target GCP project ID | deploy.yml, ml-pipeline.yml, ml-monitoring.yml |
| `GCP_REGION` | Target GCP region | deploy.yml, ml-pipeline.yml, ml-monitoring.yml |
| `GCS_BUCKET` | Runtime/model/monitoring bucket | deploy.yml, ml-pipeline.yml, ml-monitoring.yml |
| `CLOUD_RUN_SERVICE_NAME` | Cloud Run service name | deploy.yml |
| `BIGQUERY_PROJECT_ID` | BigQuery project, defaults to `GCP_PROJECT_ID` | ml-pipeline.yml, ml-monitoring.yml |
| `BIGQUERY_DATASET_RAW` | Raw listing dataset, defaults to `booli_raw` | ml-pipeline.yml, ml-monitoring.yml |
| `BIGQUERY_TABLE_LISTINGS` | Raw listing table, defaults to `listings` | ml-pipeline.yml, ml-monitoring.yml |
| `BIGQUERY_DATASET_FEATURES` | Feature dataset, defaults to `booli_features` | ml-pipeline.yml, ml-monitoring.yml |
| `BIGQUERY_TABLE_FEATURES` | Feature table, defaults to `engineered_features` | ml-pipeline.yml, ml-monitoring.yml |

Create these environment-scoped secrets:

| Secret | Description | Required For |
|--------|-------------|--------------|
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Full Workload Identity Federation provider resource | deploy.yml, ml-pipeline.yml, ml-monitoring.yml |
| `GCP_SERVICE_ACCOUNT` | Service account email allowed to impersonate via WIF | deploy.yml, ml-pipeline.yml, ml-monitoring.yml |
| `PREFECT_API_KEY` | Prefect Cloud API key, when Vertex/Prefect mode needs it | ml-pipeline.yml |
| `PREFECT_API_URL` | Prefect Cloud API URL, when needed | ml-pipeline.yml |

### Required GCP permissions:

- `deploy.yml`: Cloud Run Admin, Storage Object Viewer, Artifact Registry Reader/Writer or Container Registry permissions.
- `ml-pipeline.yml`: BigQuery Data Editor, Vertex AI User, Storage Admin for model upload.
- `ml-monitoring.yml`: BigQuery Data Viewer, Storage Object Admin for monitoring reports.

---

## 📊 Workflow Status

Check workflow status:

```bash
# List all workflows
gh workflow list

# View specific workflow runs
gh run list --workflow=ci.yml
gh run list --workflow=deploy.yml

# View details of a specific run
gh run view <run-id>

# Watch a running workflow
gh run watch
```

---

## 🛠️ Enabling/Disabling Workflows

### Disable a workflow:

1. Add to workflow file under `on:`:
   ```yaml
   on:
     workflow_dispatch:  # Only manual trigger
   ```

2. Or add at top level:
   ```yaml
   on:
     push:
       branches-ignore:
         - '**'  # Disable all automatic triggers
   ```

### Enable a workflow:

Remove the restrictions and add normal triggers:
```yaml
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
```

---

## 🔄 Typical Workflows

### Development Cycle

```
1. Create branch → CI runs automatically
2. Push commits → CI runs on each push
3. Open PR → CI runs on PR
4. Merge to main → CI runs
```

### Training New Model

```
1. Update ML code
2. Run: `gh workflow run ml-pipeline.yml -f environment=staging -f mode=local -f tune=false`
3. For cloud training, run: `gh workflow run ml-pipeline.yml -f environment=production -f mode=vertex -f tune=true`
4. Wait for training (~25-30 min)
5. Check artifacts in Actions tab
```

### Deploying Web App

```
1. Ensure CI passed on main
2. Run staging first: `gh workflow run deploy.yml -f environment=staging`
3. For production, use the protected environment: `gh workflow run deploy.yml -f environment=production`
4. Wait for deployment (~5-10 min)
5. Verify deployment URL in workflow output
```

---

## 📈 Best Practices

1. **Always wait for CI to pass** before running deploy workflows
2. **Test locally first** using `mode=local` before Vertex AI training
3. **Use semantic versioning** for training container tags (e.g., `v1.2.0`)
4. **Monitor costs** - training workflows consume cloud resources
5. **Check artifacts** after training completes
6. **Use staging environment** for deploy workflow testing

---

## 🐛 Troubleshooting

### CI fails with authentication error

**Solution:** GCS and BigQuery are disabled in CI via env vars. Check that tests don't require real cloud resources.

### Deploy workflow fails with "Invalid credentials"

**Solution:** Verify Workload Identity Federation environment secrets are configured:
```bash
gh secret list --env production
```

### Training workflow times out

**Solution:** Increase `timeout-minutes` in `ml-pipeline.yml` (default: 120 minutes).

### Container build fails

**Solution:** Check Cloud Build logs in GCP Console. Common issues:
- Missing dependencies in `vertex_ai/requirements.txt`
- Syntax errors in `vertex_ai/Dockerfile`
- Artifact Registry repository doesn't exist

---

## Related documentation

- [Architecture](../../agents/docs/architecture.md)
- [Data pipeline](../../agents/docs/data-pipeline.md)
- [ML and models](../../agents/docs/ml-and-models.md)
- [API, web, and deploy](../../agents/docs/api-web-deploy.md)
- [AGENTS.md (rules + env)](../../AGENTS.md)
- [GitHub Actions documentation](https://docs.github.com/en/actions)

---

**Last Updated:** October 2, 2025  
**Maintained By:** Estate Value Index Team
