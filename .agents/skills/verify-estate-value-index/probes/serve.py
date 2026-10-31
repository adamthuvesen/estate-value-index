"""Serve the trained models through api_server's ASGI app and report what it did.

Runs inside the temp copy. Argument: the trained model directory. No socket is opened.
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

import api_server
import estate_value_index

PREDICT = {
    "living_area": 62.0,
    "rooms": 2,
    "monthly_fee": 3100,
    "construction_year": 1958,
    "municipality": "Stockholm",
    "area": "Södermalm",
    "property_type": "Lägenhet",
}
NO_LIST_METRICS = "price_prediction_model_no_list_price_metrics.json"


def serve(models_dir: Path) -> dict[str, object]:
    api_server.MODELS_DIR = models_dir
    with TestClient(api_server.app) as client:
        health = client.get("/health")
        no_list = client.post("/predict", json=PREDICT)
        listed = client.post("/predict", json={**PREDICT, "listing_price": 5_200_000})
        malformed = [
            client.post("/predict", json={"rooms": 2}).status_code,
            client.post("/predict", json={**PREDICT, "living_area": -5}).status_code,
            client.post("/predict", json={**PREDICT, "living_area": "wide"}).status_code,
        ]
        return {
            "health_status": health.status_code,
            "health": health.json(),
            "no_list": no_list.json(),
            "no_list_status": no_list.status_code,
            "listed": listed.json(),
            "listed_status": listed.status_code,
            "malformed": malformed,
        }


def refused_artifact(models_dir: Path, stamp: str | None) -> dict[str, object]:
    """Serve a copy whose no_list metrics carry a wrong or missing package_version."""
    with tempfile.TemporaryDirectory() as scratch:
        broken = Path(scratch) / "models"
        shutil.copytree(models_dir, broken)
        metrics_path = broken / NO_LIST_METRICS
        metrics = json.loads(metrics_path.read_text())
        if stamp is None:
            del metrics["package_version"]
        else:
            metrics["package_version"] = stamp
        metrics_path.write_text(json.dumps(metrics))
        api_server.MODELS_DIR = broken
        with TestClient(api_server.app) as client:
            health = client.get("/health")
            loaded = sorted(api_server.MODEL_CACHE)
    return {"health_status": health.status_code, "loaded": loaded}


if __name__ == "__main__":
    models = Path(sys.argv[1])
    result = {
        "origin": estate_value_index.__file__,
        "served": serve(models),
        "unstamped": refused_artifact(models, None),
        "wrong_version": refused_artifact(models, "0.0.0"),
    }
    print("PROBE_RESULT " + json.dumps(result))
