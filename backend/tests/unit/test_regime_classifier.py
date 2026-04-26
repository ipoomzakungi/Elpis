import polars as pl
import pytest

from src.models.features import RegimeType
from src.services.regime_classifier import RegimeClassifier


def test_classify_bar_detects_breakout_up():
    classifier = RegimeClassifier()

    regime, confidence, reason = classifier.classify_bar(198.0, 200.0, 100.0, 150.0, 6.0, 1.3)

    assert regime == RegimeType.BREAKOUT_UP
    assert confidence == pytest.approx(0.9)
    assert "range high" in reason


def test_classify_bar_detects_breakout_down():
    classifier = RegimeClassifier()

    regime, confidence, reason = classifier.classify_bar(102.0, 200.0, 100.0, 150.0, 6.0, 1.3)

    assert regime == RegimeType.BREAKOUT_DOWN
    assert confidence == pytest.approx(0.9)
    assert "range low" in reason


def test_classify_bar_detects_range():
    classifier = RegimeClassifier()

    regime, confidence, reason = classifier.classify_bar(150.0, 200.0, 100.0, 150.0, 1.0, 1.0)

    assert regime == RegimeType.RANGE
    assert confidence == pytest.approx(0.85)
    assert "Price in range" in reason


def test_classify_bar_handles_missing_oi_without_formatting_error():
    classifier = RegimeClassifier()

    regime, confidence, reason = classifier.classify_bar(170.0, 200.0, 100.0, 150.0, None, 1.0)

    assert regime == RegimeType.AVOID
    assert confidence == pytest.approx(0.5)
    assert "N/A" in reason


def test_classify_bar_rejects_invalid_range():
    classifier = RegimeClassifier()

    regime, confidence, reason = classifier.classify_bar(100.0, 100.0, 100.0, 100.0, 1.0, 1.0)

    assert regime == RegimeType.AVOID
    assert confidence == pytest.approx(0.0)
    assert reason == "Invalid range"


def test_classify_dataframe_adds_regime_columns(sample_feature_rows: pl.DataFrame):
    classifier = RegimeClassifier()

    result = classifier.classify_dataframe(sample_feature_rows)

    assert result["regime"].to_list() == [
        RegimeType.BREAKOUT_UP.value,
        RegimeType.BREAKOUT_DOWN.value,
        RegimeType.RANGE.value,
        RegimeType.AVOID.value,
    ]
    assert {"confidence", "reason"}.issubset(result.columns)


def test_classify_dataframe_rejects_missing_columns():
    classifier = RegimeClassifier()

    with pytest.raises(ValueError, match="Missing columns"):
        classifier.classify_dataframe(pl.DataFrame({"close": [100.0]}))
