"""Run each spending CLI command without --approved and report how it ended.

Runs inside the temp copy. Argument: a scratch directory for the train case's model dir.
"""

import json
import sys
from pathlib import Path

import estate_value_index
from estate_value_index.cli.__main__ import main
from estate_value_index.utils.approval import ApprovalRequired


def cases(scratch: Path) -> dict[str, list[str]]:
    return {
        "bigquery-load": ["backfill", "--load"],
        "vertex-train": ["vertex-train"],
        "promote-model": ["promote-model", "--model-uri", "gs://verify-bucket/models/run"],
        "sync": ["sync"],
        "publish-enrichment": ["upload-enrichment"],
        "train-with-gcs": [
            "train-production-models",
            "--data-source",
            "json",
            "--data-file",
            str(scratch / "absent.jsonl"),
            "--model-dir",
            str(scratch / "models"),
        ],
    }


def outcome(argv: list[str]) -> dict[str, object]:
    try:
        code = main(argv)
    except ApprovalRequired as refusal:
        return {"refused": True, "action": refusal.action}
    except BaseException as error:
        return {"refused": False, "ended": f"{type(error).__name__}: {error}"[:300]}
    return {"refused": False, "ended": f"returned {code}"}


if __name__ == "__main__":
    scratch = Path(sys.argv[1])
    results = {name: outcome(argv) for name, argv in cases(scratch).items()}
    results_payload = {
        "origin": estate_value_index.__file__,
        "cases": results,
        "train_model_dir_created": (scratch / "models").exists(),
    }
    print("PROBE_RESULT " + json.dumps(results_payload))
