from __future__ import annotations

from unittest.mock import MagicMock

from estate_value_index.pipelines.core import data_pipeline


def test_listing_record_loader_accepts_scrapy_array_lines(tmp_path):
    listings_path = tmp_path / "listings.json"
    listings_path.write_text(
        "\n".join(
            [
                "[",
                '{"listing_id": "1", "sold_price": 1, "living_area": 40, "area": "A"},',
                '{"listing_id": "2", "sold_price": null, "living_area": 50, "area": "B"}',
                "not-json",
                "]",
            ]
        ),
        encoding="utf-8",
    )

    records = data_pipeline._load_listing_records(listings_path, MagicMock())
    summary = data_pipeline._validation_summary(
        records,
        ["listing_id", "sold_price", "living_area", "area"],
    )

    assert len(records) == 2
    assert summary["total_listings"] == 2
    assert summary["valid_listings"] == 1
    assert summary["invalid_listings"] == 1
    assert summary["validation_rate"] == 0.5
    assert summary["missing_fields"] == ["sold_price"]


def test_geocode_stage_is_skipped_without_bigquery_upload():
    geocode_task = MagicMock()

    result = data_pipeline._run_geocode_stage(
        MagicMock(),
        geocode_task,
        upload_to_bq=False,
    )

    assert result is None
    geocode_task.assert_not_called()


def test_geocode_stage_records_failure_without_raising():
    def fail_geocode(batch_size):
        raise RuntimeError(f"nope at {batch_size}")

    result = data_pipeline._run_geocode_stage(
        MagicMock(),
        fail_geocode,
        upload_to_bq=True,
    )

    assert result == {"error": "nope at 200", "success": False}


def test_sync_stage_attaches_verification_result():
    result = data_pipeline._run_sync_stage(
        MagicMock(),
        lambda: {"success": True, "listings_count": 12},
        lambda: {"in_sync": True},
        sync_after_upload=True,
        upload_to_bq=True,
    )

    assert result == {
        "success": True,
        "listings_count": 12,
        "verification": {"in_sync": True},
    }


def test_sync_stage_records_failure_without_raising():
    def fail_sync():
        raise RuntimeError("sync failed")

    result = data_pipeline._run_sync_stage(
        MagicMock(),
        fail_sync,
        lambda: {"in_sync": True},
        sync_after_upload=True,
        upload_to_bq=True,
    )

    assert result == {"error": "sync failed", "success": False}
