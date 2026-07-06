from pathlib import Path


def test_vertex_training_image_uses_locked_extras():
    dockerfile = Path("vertex_ai/Dockerfile").read_text()

    assert "uv export --frozen" in dockerfile
    assert "--extra ml" in dockerfile
    assert "--extra monitoring" in dockerfile
    assert "--extra vertex" in dockerfile
    assert "--extra geo" in dockerfile


def test_vertex_training_image_uses_production_cli():
    dockerfile = Path("vertex_ai/Dockerfile").read_text()

    assert '"estate_value_index.cli", "train-production-models"' in dockerfile
    assert "train_model.py" not in dockerfile


def test_serving_image_contains_feature_runtime_requirements():
    dockerfile = Path("Dockerfile").read_text()

    assert "uv export --frozen" in dockerfile
    assert "--extra geo" in dockerfile
    assert "COPY data/reference/ /app/data/reference/" in dockerfile
    assert "USER appuser" in dockerfile
