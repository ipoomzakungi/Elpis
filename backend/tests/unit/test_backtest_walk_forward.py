from src.backtest.validation import generate_walk_forward_splits
from src.models.backtest import ValidationSplitStatus, WalkForwardConfig
from tests.helpers.test_backtest_validation_data import make_validation_feature_rows


def test_generate_walk_forward_splits_are_chronological_and_non_overlapping():
    features = make_validation_feature_rows(row_count=12)
    config = WalkForwardConfig(split_count=3, minimum_rows_per_split=3)

    splits = generate_walk_forward_splits(features, config)

    assert [split.split_id for split in splits] == ["split_001", "split_002", "split_003"]
    assert [split.row_count for split in splits] == [4, 4, 4]
    assert all(split.status == ValidationSplitStatus.EVALUATED for split in splits)
    assert splits[0].end_timestamp < splits[1].start_timestamp
    assert splits[1].end_timestamp < splits[2].start_timestamp
    assert splits[0].frame["timestamp"].to_list() == features["timestamp"][:4].to_list()
    assert splits[1].frame["timestamp"].to_list() == features["timestamp"][4:8].to_list()
    assert splits[2].frame["timestamp"].to_list() == features["timestamp"][8:12].to_list()


def test_generate_walk_forward_splits_marks_small_windows_insufficient():
    features = make_validation_feature_rows(row_count=9)
    config = WalkForwardConfig(split_count=3, minimum_rows_per_split=4)

    splits = generate_walk_forward_splits(features, config)

    assert [split.row_count for split in splits] == [3, 3, 3]
    assert all(split.status == ValidationSplitStatus.INSUFFICIENT_DATA for split in splits)
    assert all("fewer than the configured minimum" in split.notes[0] for split in splits)
