"""Pipeline tasks call Python code directly instead of shelling out to Python scripts."""

import inspect
from pathlib import Path

import pytest


class TestFeatureMaterializationTask:
    def test_materialize_features_no_subprocess(self):
        source = Path("src/estate_value_index/pipelines/tasks/training.py").read_text()
        assert (
            "from estate_value_index.ml.feature_materialization import materialize_features"
            in source
        )

        from estate_value_index.pipelines.tasks.training import materialize_features_task

        assert "subprocess.run" not in inspect.getsource(materialize_features_task)


class TestAreaStatisticsTask:
    def test_generate_area_statistics_task_no_subprocess(self):
        from estate_value_index.pipelines.tasks.analytics import generate_area_statistics_task

        source = inspect.getsource(generate_area_statistics_task)
        assert (
            "from estate_value_index.analytics.area_statistics import generate_area_statistics"
            in source
        )
        assert "subprocess.run" not in source


class TestValueAnalysisTask:
    def test_generate_value_analysis_task_no_subprocess(self):
        from estate_value_index.pipelines.tasks.analytics import generate_value_analysis_task

        source = inspect.getsource(generate_value_analysis_task)
        assert (
            "from estate_value_index.analytics.value_analysis import generate_value_analysis"
            in source
        )
        assert "subprocess.run" not in source


class TestLocalTrainingTask:
    def test_local_training_no_subprocess(self):
        source = Path("src/estate_value_index/pipelines/core/training_pipeline.py").read_text()
        assert "from estate_value_index.cli.train_production_models import" in source
        assert "train_model.py" not in source


class TestScriptEntrypoints:
    def test_root_train_model_script_removed(self):
        assert not Path("train_model.py").exists()


class TestNoSubprocessRegressions:
    """subprocess usage must be limited to external tools (gcloud, gsutil, etc.)."""

    def test_training_tasks_subprocess_usage(self):
        source = Path("src/estate_value_index/pipelines/tasks/training.py").read_text()

        # Extract just the materialize_features_task function body
        lines = source.split("\n")
        in_materialize_task = False
        materialize_task_lines = []
        for line in lines:
            if "def materialize_features_task" in line:
                in_materialize_task = True
            if in_materialize_task:
                materialize_task_lines.append(line)
                if line.startswith("def ") and "materialize_features_task" not in line:
                    break
                if line.startswith("@task") and len(materialize_task_lines) > 10:
                    break

        materialize_task_source = "\n".join(materialize_task_lines)
        assert "subprocess.run" not in materialize_task_source, (
            "materialize_features_task still uses subprocess.run"
        )

    def test_analytics_tasks_subprocess_usage(self):
        from estate_value_index.pipelines.tasks import analytics

        source = inspect.getsource(analytics)
        assert "subprocess.run" not in source or (
            "generate_area_statistics.py" not in source
            and "generate_value_analysis.py" not in source
        ), "Found Python subprocess call in analytics.py"

    def test_training_pipeline_subprocess_usage(self):
        from estate_value_index.pipelines.core import training_pipeline

        source = inspect.getsource(training_pipeline)
        assert "train_model.py" not in source


class TestImportStructure:
    def test_training_imports_materialize_features(self):
        from estate_value_index.pipelines.tasks import training

        source = Path("src/estate_value_index/pipelines/tasks/training.py").read_text()
        assert (
            hasattr(training, "materialize_features")
            or "from estate_value_index.ml.feature_materialization import materialize_features"
            in source
        )

    def test_analytics_imports_generators(self):
        source = Path("src/estate_value_index/pipelines/tasks/analytics.py").read_text()
        assert (
            "from estate_value_index.analytics.area_statistics import generate_area_statistics"
            in source
        )
        assert (
            "from estate_value_index.analytics.value_analysis import generate_value_analysis"
            in source
        )

    def test_training_pipeline_imports_training_workflow(self):
        source = Path("src/estate_value_index/pipelines/core/training_pipeline.py").read_text()
        assert "from estate_value_index.cli.train_production_models import" in source


class TestUnifiedCliSubcommands:
    def test_areas_dispatches_with_parsed_args(self, monkeypatch):
        from estate_value_index.cli import __main__ as cli_main

        captured = {}

        def fake_areas_main(argv):
            captured["argv"] = argv
            return 0

        monkeypatch.setattr(cli_main, "_load_handler", lambda command: fake_areas_main)

        result = cli_main.main(["areas", "--data-source", "json", "--output", "out.json"])

        assert result == 0
        assert captured["argv"] == ["--data-source", "json", "--output", "out.json"]

    def test_value_analysis_dispatches_with_parsed_args(self, monkeypatch, tmp_path):
        from estate_value_index.cli import __main__ as cli_main

        captured = {}

        def fake_value_analysis_main(argv):
            captured["argv"] = argv
            return 0

        monkeypatch.setattr(cli_main, "_load_handler", lambda command: fake_value_analysis_main)
        output = tmp_path / "value.json"

        result = cli_main.main(
            ["value-analysis", "--output", str(output), "--model-type", "no_list_price"]
        )

        assert result == 0
        assert captured["argv"] == ["--output", str(output), "--model-type", "no_list_price"]

    def test_area_metrics_dispatches_with_parsed_args(self, monkeypatch):
        from estate_value_index.cli import __main__ as cli_main

        captured = {}

        def fake_area_metrics_main(argv):
            captured["argv"] = argv
            return 0

        monkeypatch.setattr(cli_main, "_load_handler", lambda command: fake_area_metrics_main)

        result = cli_main.main(["area-metrics"])

        assert result == 0
        assert captured["argv"] == []


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
