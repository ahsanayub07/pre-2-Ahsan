import numpy as np
import pytest

import classify


def test_mcnemar_exact():
    assert classify.mcnemar_exact(0, 0) == 1.0
    assert classify.mcnemar_exact(5, 5) == 1.0
    assert abs(classify.mcnemar_exact(10, 0) - 2 * 0.5 ** 10) < 1e-12


def test_domain_majority():
    m = classify.domain_majority(["a", "a", "a", "b"], ["x", "x", "y", "z"])
    assert m == {"a": "x", "b": "z"}


def test_head_to_head():
    h = classify.head_to_head(["a", "a", "b", "b"], ["a", "a", "a", "b"], ["a", "b", "a", "a"])
    assert h == {"both_right": 1, "classifier_only_right": 2, "rules_only_right": 0,
                 "both_wrong": 1, "exact_p_value": 0.5}


def test_read_columns(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("id,domain,category,extra\n1,a.com,tech,zz\n2,b.com,other,yy\n", encoding="utf-8")
    assert classify.read_columns(p, ["id", "category"]) == {"id": ["1", "2"], "category": ["tech", "other"]}
    with pytest.raises(ValueError):
        classify.read_columns(p, ["nope"])
    assert classify.read_id_list(p) == {1, 2}


def test_schemes_learn_and_unseen_removes_whole_websites():
    rng = np.random.default_rng(0)
    classes = ["a", "b", "c"]
    centres = {c: rng.normal(size=12) * 3 for c in classes}
    y_pool = [classes[i % 3] for i in range(450)]
    X_pool = np.array([centres[c] + rng.normal(size=12) * 0.5 for c in y_pool], dtype=np.float32)
    dom_pool = [f"site{i % 15}" for i in range(450)]
    y_test = [classes[i % 3] for i in range(30)]
    X_test = np.array([centres[c] + rng.normal(size=12) * 0.5 for c in y_test], dtype=np.float32)
    dom_test = [f"site{i % 10}" for i in range(30)]
    lines = []
    seen, unseen = classify.run_schemes(X_pool, y_pool, dom_pool, X_test, y_test, dom_test, log=lines.append)
    assert np.mean(np.array(seen) == np.array(y_test)) > 0.9
    assert np.mean(np.array(unseen, dtype=object) == np.array(y_test, dtype=object)) > 0.9
    assert len(lines) == 6                                   # 1 seen + 5 folds
    assert all(u in classes for u in unseen)
