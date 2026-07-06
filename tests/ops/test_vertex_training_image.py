from pathlib import Path


def test_vertex_training_image_installs_monitoring_extra():
    dockerfile = Path("vertex_ai/Dockerfile").read_text()

    assert 'uv pip install --system ".[ml,monitoring,vertex]"' in dockerfile


def test_vertex_training_image_uses_production_cli():
    dockerfile = Path("vertex_ai/Dockerfile").read_text()

    assert '"estate_value_index.cli", "train-production-models"' in dockerfile
    assert "train_model.py" not in dockerfile
