from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from estate_value_index.pipelines.core import data_pipeline


def test_listing_record_loader_accepts_jsonl_and_skips_invalid_lines(tmp_path):
    listings_path = tmp_path / "listings.jsonl"
    listings_path.write_text(
        "\n".join(
            [
                '{"listing_id": "1", "sold_price": 1, "living_area": 40, "area": "A"}',
                '{"listing_id": "2", "sold_price": null, "living_area": 50, "area": "B"}',
                "not-json",
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


def test_geocode_stage_raises_failure():
    def fail_geocode(batch_size):
        raise RuntimeError(f"nope at {batch_size}")

    with pytest.raises(RuntimeError, match="nope at 200"):
        data_pipeline._run_geocode_stage(
            MagicMock(),
            fail_geocode,
            upload_to_bq=True,
        )


def test_sync_stage_attaches_verification_result():
    result = data_pipeline._run_sync_stage(
        MagicMock(),
        lambda: {"success": True, "records_synced": 12},
        lambda: {"in_sync": True},
        sync_after_upload=True,
        upload_to_bq=True,
    )

    assert result == {
        "success": True,
        "records_synced": 12,
        "verification": {"in_sync": True},
    }


def test_sync_stage_raises_failure():
    def fail_sync():
        raise RuntimeError("sync failed")

    with pytest.raises(RuntimeError, match="sync failed"):
        data_pipeline._run_sync_stage(
            MagicMock(),
            fail_sync,
            lambda: {"in_sync": True},
            sync_after_upload=True,
            upload_to_bq=True,
        )


def test_fetch_booli_api_forwards_config_and_output(tmp_path, monkeypatch):
    output_file = tmp_path / "listings.jsonl"
    config_file = tmp_path / "config.json"
    config_file.write_text('{"search_parameters": {}}', encoding="utf-8")
    calls = {}

    def fake_fetch(**kwargs):
        calls.update(kwargs)
        output_file.write_text(
            '{"listing_id": "1", "sold_price": 1, "living_area": 40, "area": "A"}\n',
            encoding="utf-8",
        )
        return output_file

    monkeypatch.setattr(data_pipeline, "scrape_booli_api_window", fake_fetch)

    result = data_pipeline.fetch_booli_api.fn(
        max_pages=3,
        config_file=str(config_file),
        output_file=output_file,
    )

    assert result == output_file
    assert calls == {
        "config_file": config_file,
        "output_file": output_file,
        "max_pages": 3,
    }


def test_validate_listings_fails_below_threshold(tmp_path):
    output_file = tmp_path / "mixed.jsonl"
    output_file.write_text(
        '{"listing_id": "1", "sold_price": 1, "living_area": 40, "area": "A"}\n'
        '{"listing_id": "2", "sold_price": null, "living_area": 50, "area": "B"}\n',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="validation rate"):
        data_pipeline.validate_listings.fn(output_file, min_validation_rate=0.75)


def test_validation_summary_treats_blank_required_strings_as_missing():
    summary = data_pipeline._validation_summary(
        [{"listing_id": " ", "sold_price": 1, "living_area": 40, "area": "A"}],
        ["listing_id", "sold_price", "living_area", "area"],
    )

    assert summary["valid_listings"] == 0
    assert summary["missing_fields"] == ["listing_id"]
