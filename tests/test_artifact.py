import pytest

from src.model.artifact import load_model_artifact, save_model_artifact


class DummyModel:
    """Modelo de juguete: solo necesita .predict(), como cualquier
    modelo real (sklearn, LightGBM...). Sirve para probar que el
    contrato de guardado/carga es agnostico al algoritmo."""

    def predict(self, X):
        return [42.0] * len(X)


@pytest.fixture
def artifact_paths(tmp_path):
    return tmp_path / "model.joblib", tmp_path / "model_metadata.json"


def test_save_and_load_roundtrip(artifact_paths):
    model_path, metadata_path = artifact_paths
    model = DummyModel()

    saved_metadata = save_model_artifact(
        model,
        feature_columns=["hour", "dayofweek"],
        model_type="dummy",
        metrics={"mae": 1.23},
        model_path=model_path,
        metadata_path=metadata_path,
    )

    loaded_model, loaded_metadata = load_model_artifact(
        model_path=model_path, metadata_path=metadata_path
    )

    assert loaded_model.predict([1, 2, 3]) == [42.0, 42.0, 42.0]
    assert loaded_metadata == saved_metadata


def test_metadata_has_required_fields(artifact_paths):
    model_path, metadata_path = artifact_paths
    metadata = save_model_artifact(
        DummyModel(),
        feature_columns=["hour"],
        model_type="dummy",
        metrics={},
        model_path=model_path,
        metadata_path=metadata_path,
    )

    for field in ["model_type", "model_version", "trained_at", "target", "feature_columns", "metrics"]:
        assert field in metadata


def test_model_version_equals_trained_at(artifact_paths):
    model_path, metadata_path = artifact_paths
    metadata = save_model_artifact(
        DummyModel(),
        feature_columns=["hour"],
        model_type="dummy",
        metrics={},
        model_path=model_path,
        metadata_path=metadata_path,
    )
    assert metadata["model_version"] == metadata["trained_at"]


def test_load_missing_artifact_raises_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="entrenamiento"):
        load_model_artifact(
            model_path=tmp_path / "nope.joblib",
            metadata_path=tmp_path / "nope.json",
        )


def test_default_target_is_precio_spot(artifact_paths):
    model_path, metadata_path = artifact_paths
    metadata = save_model_artifact(
        DummyModel(),
        feature_columns=["hour"],
        model_type="dummy",
        metrics={},
        model_path=model_path,
        metadata_path=metadata_path,
    )
    assert metadata["target"] == "precio_spot"
