from __future__ import annotations

import argparse
from pathlib import Path

from estate_value_index.analytics.micro_areas import (
    DEFAULT_OUTPUT_DIR,
    MICRO_AREA_MIN_PRIOR_COUNT,
    generate_micro_area_report,
)


def main(argv: list[str] | None = None, *, args=None) -> int:
    if args is None:
        parser = argparse.ArgumentParser(description="Generate H3 micro-area premium reports")
        parser.add_argument("--data-file", type=Path, default=None)
        parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
        parser.add_argument("--min-count", type=int, default=MICRO_AREA_MIN_PRIOR_COUNT)
        args = parser.parse_args(argv)

    summary = generate_micro_area_report(
        data_file=args.data_file,
        output_dir=args.output_dir,
        min_count=args.min_count,
    )
    print(
        "Micro-area report complete: "
        f"{summary['eligible_cells']}/{summary['cells']} eligible cells, "
        f"{summary['eligible_listing_rows']} listings covered"
    )
    print(f"Output directory: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
