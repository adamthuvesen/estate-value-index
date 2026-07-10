from pathlib import Path


def test_catchup_script_requires_cloud_targets_for_real_runs() -> None:
    script = Path("scripts/run_catchup_backfill.sh").read_text(encoding="utf-8")

    assert 'GCP_PROJECT_ID="${GCP_PROJECT_ID:-}"' in script
    assert 'GCS_BUCKET="${GCS_BUCKET:-}"' in script
    assert "require_env GCP_PROJECT_ID" in script
    assert "require_env GCS_BUCKET" in script
    assert "estate-value-index-data-production" not in script
