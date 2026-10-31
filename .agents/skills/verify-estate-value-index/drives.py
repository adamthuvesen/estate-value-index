"""The four drives. Each runs the real CLI or ASGI app on a temp copy and asserts the result."""

import hashlib
import json
import re
import sys
import threading
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fixtures
from harness import DriveFailure, Run, check

MODELS = ("no_list_price", "with_list_price")
type Summary = dict[str, dict[str, Any]]
SHA256 = re.compile(r"[0-9a-f]{64}")
# The control passes only when the train drive fails with exactly this text.
CONTROL_FAILURE = (
    f"data_fingerprint.rows in no_list_price metrics: expected {fixtures.ROWS}, "
    f"got {fixtures.ROWS + 1}"
)


@dataclass(frozen=True)
class Drive:
    proves: str
    paths: list[str]
    run: Callable[[Run, Shared], str]


class Shared:
    """Models trained once per verify run; the serve and analytics drives read them."""

    def __init__(self, evidence: Path, plant: Callable[[Run], None] | None = None) -> None:
        self.evidence = evidence
        self.plant = plant
        self.lock = threading.Lock()
        self.trained: tuple[Run, Summary] | BaseException | None = None

    def cleanup(self) -> None:
        if isinstance(self.trained, tuple):
            self.trained[0].cleanup()

    def models(self) -> tuple[Run, Summary]:
        with self.lock:
            if self.trained is None:
                try:
                    self.trained = self._train()
                except DriveFailure as error:
                    self.trained = error
            if isinstance(self.trained, BaseException):
                raise DriveFailure(f"train did not produce models: {self.trained}")
            return self.trained

    def _train(self) -> tuple[Run, Summary]:
        run = Run(self.evidence, "train")
        if self.plant:
            self.plant(run)
        listings = run.home / "listings.jsonl"
        listings.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in fixtures.synthetic_listings())
        )
        summary = run.home / "summary.json"
        run.cmd(
            [
                sys.executable, "-m", "estate_value_index.cli", "train-production-models",
                "--data-source", "json", "--data-file", str(listings),
                "--model-dir", str(run.home / "models"), "--n-splits", "2",
                "--summary", str(summary),
            ]
        )  # fmt: skip
        if not summary.exists():
            raise DriveFailure("train-production-models wrote no --summary file")
        return run, json.loads(summary.read_text())


def drive_train(run: Run, shared: Shared) -> str:
    trained, summary = shared.models()
    check(sorted(summary), sorted(MODELS), "models in the training summary")
    version = tomllib.loads((trained.copy / "pyproject.toml").read_text())["project"]["version"]
    fingerprints = []
    for model_id in MODELS:
        artifacts = summary[model_id]["artifacts"]
        for kind, path in artifacts.items():
            if not Path(path).is_file():
                raise DriveFailure(f"{model_id} {kind} artifact is missing: {path}")
        model = Path(artifacts["model"])
        sidecar = Path(artifacts["model_sha256"]).read_text().split()[0]
        check(sidecar, hashlib.sha256(model.read_bytes()).hexdigest(), f"{model_id} sha256 sidecar")
        metrics = json.loads(Path(artifacts["metrics"]).read_text())
        check(metrics.get("package_version"), version, f"package_version in {model_id} metrics")
        fingerprint = metrics.get("data_fingerprint") or {}
        check(
            fingerprint.get("rows"),
            fixtures.ROWS,
            f"data_fingerprint.rows in {model_id} metrics",
        )
        if not SHA256.fullmatch(str(fingerprint.get("sha256"))):
            raise DriveFailure(f"data_fingerprint.sha256 in {model_id} metrics is not a sha256")
        fingerprints.append(fingerprint)
    check(fingerprints[0], fingerprints[1], "data fingerprint of both models")
    return f"both models written, stamped {version}, fingerprint over {fixtures.ROWS} rows"


def _metrics(summary: Summary, model_id: str) -> dict[str, Any]:
    return json.loads(Path(summary[model_id]["artifacts"]["metrics"]).read_text())


def _assert_prediction(body: dict[str, Any], model_id: str) -> None:
    check(body["model_id"], model_id, f"model_id for the {model_id} request")
    price = body["predicted_price"]
    if not isinstance(price, float) or not 500_000 < price < 100_000_000:
        raise DriveFailure(f"{model_id} predicted_price is not a plausible SEK value: {price!r}")
    factors = body["estimate_range_factors"]
    if not isinstance(factors, dict):
        raise DriveFailure(f"{model_id} response carries no typed estimate_range_factors")
    pooled = factors["pooled"]
    if not 0 < pooled["lower"] < pooled["upper"]:
        raise DriveFailure(f"{model_id} pooled range is not 0 < lower < upper: {pooled!r}")
    check(
        factors["upper_percentile"] - factors["lower_percentile"],
        factors["interval_pct"],
        f"{model_id} interval_pct",
    )
    if not factors["buckets"]:
        raise DriveFailure(f"{model_id} range has no buckets")


def drive_serve(run: Run, shared: Shared) -> str:
    _, summary = shared.models()
    models_dir = Path(summary["no_list_price"]["artifacts"]["model"]).parent
    result = run.probe("serve.py", str(models_dir))
    served: dict[str, Any] = result["served"]
    check(served["health_status"], 200, "/health status")
    health: dict[str, Any] = served["health"]
    check(sorted(health["models_loaded"]), sorted(MODELS), "models in /health")
    version = tomllib.loads((run.copy / "pyproject.toml").read_text())["project"]["version"]
    for model_id in MODELS:
        info = health["models"][model_id]
        check(info["package_version"], version, f"/health package_version of {model_id}")
        check(
            info["data_fingerprint"],
            _metrics(summary, model_id)["data_fingerprint"],
            f"/health data_fingerprint of {model_id}",
        )
    check(served["no_list_status"], 200, "predict status without listing_price")
    check(served["listed_status"], 200, "predict status with listing_price")
    _assert_prediction(served["no_list"], "no_list_price")
    _assert_prediction(served["listed"], "with_list_price")
    check(served["malformed"], [422, 422, 422], "status of three malformed predict requests")
    for label in ("unstamped", "wrong_version"):
        refused: dict[str, Any] = result[label]
        check(refused["loaded"], ["with_list_price"], f"models loaded with a {label} artifact")
        check(refused["health_status"], 503, f"/health with a {label} artifact")
    return "health reports both models and fingerprints, predict returns a typed range, bad input gets 422, unstamped artifact refused"


def drive_analytics(run: Run, shared: Shared) -> str:
    _, summary = shared.models()
    no_list = summary["no_list_price"]["artifacts"]
    models_dir = Path(no_list["model"]).parent
    listings = run.home / "listings.jsonl"
    listings.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in fixtures.synthetic_listings())
    )
    derived = run.home / "derived"
    value, areas, overall = (derived / name for name in (
        "value_analysis.json", "area_statistics.json", "overall_statistics.json"
    ))  # fmt: skip
    evi = [sys.executable, "-m", "estate_value_index.cli"]
    run.cmd([
        *evi, "value-analysis", "--data-file", str(listings), "--models-dir", str(models_dir),
        "--model-type", "no_list_price", "--output", str(value),
    ])  # fmt: skip
    run.cmd([
        *evi, "areas", "--data-source", "json", "--raw-listings", str(listings),
        "--feature-context", no_list["context"], "--value-analysis", str(value),
        "--output", str(areas),
    ])  # fmt: skip
    run.cmd([
        *evi, "overall-stats", "--data-source", "json", "--raw-listings", str(listings),
        "--value-analysis", str(value), "--output", str(overall),
    ])  # fmt: skip
    for path in (value, areas, overall):
        if not path.is_file():
            raise DriveFailure(f"{path.name} was not written")
    counts = run.probe("analytics.py", str(value), str(areas), str(overall))
    for key in ("value_properties", "areas", "overall_properties"):
        if counts[key] < 1:
            raise DriveFailure(f"{key} is {counts[key]}; the derived file is empty")
    check(counts["overall_properties"], fixtures.ROWS, "listings counted in overall_statistics")
    stale = run.cmd(["just", "types-check"], expect_exit=None)
    if stale.returncode != 0:
        raise DriveFailure(f"just types-check: {(stale.stdout + stale.stderr).strip()[-300:]}")
    return (
        f"value, area, and overall JSON validate ({counts['value_properties']} properties, "
        f"{counts['areas']} areas) and the generated TypeScript types are current"
    )


# The environment makes every refusal reachable: GCS on, a project, and a bucket.
SPEND_ENV = {
    "GCS_ENABLED": "true",
    "GCP_PROJECT_ID": "verify-project",
    "GCS_BUCKET": "verify-bucket",
}
SPEND_CASES = (
    "bigquery-load",
    "vertex-train",
    "promote-model",
    "sync",
    "publish-enrichment",
    "train-with-gcs",
)


def drive_spend_refusal(run: Run, shared: Shared) -> str:
    result = run.probe("refusal.py", str(run.home / "spend"), extra_env=SPEND_ENV)
    check(sorted(result["cases"]), sorted(SPEND_CASES), "spending commands driven")
    for name, case in result["cases"].items():
        if not case["refused"]:
            raise DriveFailure(f"{name} was not refused without --approved: {case['ended']}")
        if not case["action"]:
            raise DriveFailure(f"{name} refused without naming the action")
    check(result["train_model_dir_created"], False, "train model dir created before the refusal")
    real = run.cmd(
        [sys.executable, "-m", "estate_value_index.cli", "upload-enrichment"],
        extra_env=SPEND_ENV,
        expect_exit=None,
    )
    if real.returncode == 0 or not real.stderr.strip() or real.stdout.strip():
        raise DriveFailure(
            f"upload-enrichment process: expected a non-zero exit with only stderr, "
            f"got exit {real.returncode}, stdout {real.stdout.strip()[:80]!r}"
        )
    return f"{len(SPEND_CASES)} spending commands refuse without --approved; the process exits {real.returncode}"


DRIVES = {
    "train": Drive(
        "train-production-models on a seeded synthetic frame writes both stamped, fingerprinted models",
        ["src/estate_value_index/ml/**", "src/estate_value_index/model_artifacts.py",
         "src/estate_value_index/cli/train_production_models.py"],
        drive_train,
    ),
    "serve": Drive(
        "api_server over ASGI reports models and fingerprints, predicts with a range, and refuses bad input and unstamped artifacts",
        ["api_server.py", "src/estate_value_index/model_artifacts.py",
         "src/estate_value_index/ml/**"],
        drive_serve,
    ),
    "analytics": Drive(
        "the three derived JSON files validate against web_json and the generated TypeScript types are current",
        ["src/estate_value_index/analytics/**", "src/estate_value_index/cli/generate_*.py",
         "scripts/export_web_schema.py", "web/src/lib/generated/**"],
        drive_analytics,
    ),
    "spend-refusal": Drive(
        "every spending command refuses without --approved and no tripwire is hit",
        ["src/estate_value_index/utils/approval.py", "src/estate_value_index/utils/gcs.py",
         "src/estate_value_index/cli/**", "src/estate_value_index/ingestion/**",
         "src/estate_value_index/analytics/publish.py"],
        drive_spend_refusal,
    ),
}  # fmt: skip
