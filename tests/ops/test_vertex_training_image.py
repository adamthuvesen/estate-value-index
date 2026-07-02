from pathlib import Path


def test_vertex_training_image_installs_monitoring_extra():
    dockerfile = Path("vertex_ai/Dockerfile").read_text()

    assert 'uv pip install --system ".[ml,monitoring,vertex]"' in dockerfile
