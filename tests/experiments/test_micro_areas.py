from __future__ import annotations

import json

from estate_value_index.experiments.micro_areas import generate_micro_area_report


def test_generate_micro_area_report_writes_outputs(tmp_path) -> None:
    data_file = tmp_path / "listings.jsonl"
    rows = [
        {
            "listing_id": f"L{i}",
            "area": "Södermalm",
            "sold_price": 4_000_000 + i * 10_000,
            "living_area": 50,
            "latitude": 59.315 + i * 0.00001,
            "longitude": 18.07,
            "property_type": "Lägenhet",
        }
        for i in range(3)
    ]
    data_file.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "micro_areas"
    summary = generate_micro_area_report(data_file=data_file, output_dir=output_dir, min_count=1)

    assert summary["rows"] == 3
    assert (output_dir / "README.md").exists()
    assert (output_dir / "micro_area_cells.csv").exists()
    assert (output_dir / "summary.json").exists()
