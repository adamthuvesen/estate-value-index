# GitHub Actions Workflows

This directory contains CI/CD workflows for the Estate Value Index project.

## 📋 Overview

| Workflow | Status | Trigger | Purpose |
|----------|--------|---------|---------|
| **ci.yml** | ✅ Enabled | Push, PR | Run tests and linting |
| **deploy.yml** | ⏸️ Disabled | Manual | Deploy web app to Cloud Run |
| **build-training-container.yml** | ⏸️ Disabled | Manual | Build Vertex AI training container |
| **train-model.yml** | ⏸️ Disabled | Manual | Run ML training job |

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
gh workflow run deploy.yml -f environment=production
gh workflow run deploy.yml -f environment=staging
```

### Parameters:

| Parameter | Options | Default | Description |
|-----------|---------|---------|-------------|
| `environment` | production, staging | production | Deployment target |

---

## 🐳 Build Training Container (Disabled)

**File:** `build-training-container.yml`  
**Triggers:** Manual only (`workflow_dispatch`)

### What it does:

1. Builds Vertex AI training container
2. Pushes to Artifact Registry
3. Makes available for training jobs

**When to use:**
- After updating `src/estate_value_index/ml/` code
- After modifying `train_model.py`
- After changing `vertex_ai/Dockerfile`

### Usage:

```bash
# Via GitHub UI:
Actions → Build Training Container → Run workflow

# Via GitHub CLI:
gh workflow run build-training-container.yml
gh workflow run build-training-container.yml -f image_tag=v1.2.0
```

### Parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `image_tag` | string | latest | Container image tag |

### Output:

```
Image: europe-north1-docker.pkg.dev/estate-value-index/vertex-training/lgbm-trainer:latest
```

---

## 🧠 Train Model (Disabled)

**File:** `train-model.yml`  
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
gh workflow run train-model.yml -f mode=vertex -f tune=false -f machine_type=n1-standard-4

# Production training (with tuning)
gh workflow run train-model.yml -f mode=vertex -f tune=true -f machine_type=n1-standard-4

# Local training (for testing)
gh workflow run train-model.yml -f mode=local -f tune=false
```

### Parameters:

| Parameter | Options | Default | Description |
|-----------|---------|---------|-------------|
| `tune` | true, false | false | Enable hyperparameter tuning |
| `machine_type` | n1-standard-2/4/8 | n1-standard-4 | Vertex AI machine type |
| `mode` | vertex, local | vertex | Training mode |

### Costs:

| Configuration | Duration | Estimated Cost |
|---------------|----------|----------------|
| Quick (no tuning) | ~10-15 min | ~$0.10 |
| Production (tuning) | ~25-30 min | ~$0.35 |
| Local | ~5-10 min | $0 |

---

## 🔐 Required Secrets

The following secrets must be configured in GitHub repository settings:

| Secret | Description | Required For |
|--------|-------------|--------------|
| `GCP_SA_KEY` | GCP service account JSON key | deploy.yml, build-training-container.yml, train-model.yml |

### Setting up secrets:

```bash
# Via GitHub UI:
Settings → Secrets and variables → Actions → New repository secret

# Via GitHub CLI:
gh secret set GCP_SA_KEY < path/to/service-account-key.json
```

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
2. Run: gh workflow run build-training-container.yml
3. Wait for container build (~5-10 min)
4. Run: gh workflow run train-model.yml -f mode=vertex -f tune=true
5. Wait for training (~25-30 min)
6. Check artifacts in Actions tab
```

### Deploying Web App

```
1. Ensure CI passed on main
2. Run: gh workflow run deploy.yml -f environment=production
3. Wait for deployment (~5-10 min)
4. Verify deployment URL in workflow output
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

**Solution:** Verify `GCP_SA_KEY` secret is properly configured:
```bash
gh secret list
```

### Training workflow times out

**Solution:** Increase `timeout-minutes` in `train-model.yml` (default: 90 minutes).

### Container build fails

**Solution:** Check Cloud Build logs in GCP Console. Common issues:
- Missing dependencies in `vertex_ai/requirements.txt`
- Syntax errors in `vertex_ai/Dockerfile`
- Artifact Registry repository doesn't exist

---

## Related documentation

- [Project / architecture / ops](../../docs/PROJECT.md)
- [Agent guide](../../agents/docs/AGENT.md)
- [AGENTS.md (rules + env)](../../AGENTS.md)
- [GitHub Actions documentation](https://docs.github.com/en/actions)

---

**Last Updated:** October 2, 2025  
**Maintained By:** Estate Value Index Team





