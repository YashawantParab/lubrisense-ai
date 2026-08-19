from ml_service.config.loader import load_anomaly_config, load_classifier_config


def test_load_anomaly_config_from_real_file() -> None:
    config = load_anomaly_config()
    assert config.model_id == "LUBRICATION_ANOMALY_V1"
    assert config.feature_set == "LUBRICATION_ANOMALY_V1"
    assert config.n_estimators > 0
    assert 0.0 < config.contamination < 0.5
    assert 0.0 < config.target_validation_fpr < 1.0
    assert "pressure.current" in config.minimum_required_features


def test_load_classifier_config_from_real_file() -> None:
    config = load_classifier_config()
    assert config.model_id == "FAILURE_CLASSIFICATION_V1"
    assert 0.0 < config.unknown_confidence_threshold < 1.0
    assert config.confidence_moderate_threshold < config.confidence_high_threshold
    assert config.baseline.max_iter > 0
    assert config.primary.max_iter > 0
