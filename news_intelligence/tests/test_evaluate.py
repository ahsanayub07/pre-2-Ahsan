import numpy as np
import pytest

import compare_models
import evaluate


def test_wilson():
    lo, hi = evaluate.wilson(50, 100)
    assert 0.40 < lo < 0.41 and 0.59 < hi < 0.60
    assert evaluate.wilson(0, 0) == (0.0, 0.0)
    assert evaluate.wilson(10, 10)[1] == 1.0


def test_score_perfect_and_wrong():
    s = evaluate.score(["a", "b", "a"], ["a", "b", "a"], classes=["a", "b"])
    assert s["accuracy"] == 1.0 and s["macro_f1"] == 1.0
    s = evaluate.score(["a", "a"], ["b", "b"], classes=["a", "b"])
    assert s["accuracy"] == 0.0 and s["per_class"]["a"]["recall"] == 0.0


def test_macro_f1_skips_absent_classes():
    s = evaluate.score(["a", "a"], ["a", "a"], classes=["a", "b", "c"])
    assert s["macro_f1"] == 1.0 and s["per_class"]["b"]["n"] == 0


def test_majority():
    assert evaluate.majority_baseline(["x", "x", "y"]) == {"class": "x", "accuracy": 0.6667}


def test_load_labels(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_text('review_id,article_id,your_label\n"1","10","technology"\n2,11,uncertain\n'
                 '3,12,other\n4,13,health\n', encoding="utf-8")
    b.write_text("review_id,article_id,your_label\n1,10,technology\n2,12,politics\n3,14,not_news\n",
                 encoding="utf-8")
    labels, rep = evaluate.load_labels([a, b])
    assert labels == {10: "technology", 13: "health"}          # 12 conflicted, 11/14 not classes
    assert rep["dropped"] == {"label_uncertain": 1, "conflict_between_files": 1, "label_not_news": 1}


def test_load_labels_bad_columns(tmp_path):
    f = tmp_path / "x.csv"
    f.write_text("id,label\n1,a\n", encoding="utf-8")
    with pytest.raises(ValueError):
        evaluate.load_labels([f])


def test_parse_config():
    assert compare_models.parse_config("org/model:256") == ("org/model", 256)
    with pytest.raises(ValueError):
        compare_models.parse_config("model")


def test_cv_learns_separable_data_and_control_is_near_chance():
    rng = np.random.default_rng(0)
    classes = ["a", "b", "c"]
    y = [classes[i % 3] for i in range(150)]
    centres = {c: rng.normal(size=16) * 3 for c in classes}
    X = np.array([centres[c] + rng.normal(size=16) * 0.5 for c in y])
    groups = [f"site{i % 10}" for i in range(150)]
    res = compare_models.evaluate_setup(X, y, groups)
    assert res["accuracy"] > 0.95
    assert res["shuffled_label_control_accuracy"] < 0.55
