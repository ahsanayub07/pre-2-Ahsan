import numpy as np

import config
import predict_demo
from svm_model import Pipeline


def test_all_classes_have_a_sample():
    assert set(predict_demo.SAMPLES) == set(config.CLASSES)
    for title, text in predict_demo.SAMPLES.values():
        assert title and len(text.split()) >= 60


def tiny_data(seed=0):
    rng = np.random.default_rng(seed)
    classes = config.CLASSES
    centres = rng.normal(size=(6, 24)) * 3
    y = [classes[i % 6] for i in range(360)]
    X = np.array([centres[classes.index(c)] + rng.normal(size=24) * 0.4 for c in y], dtype=np.float32)
    return {"X_pool": X, "y_pool": y}, centres


def test_train_and_predict_every_model(monkeypatch):
    monkeypatch.setitem(predict_demo.svm_classify.SCRATCH, "epochs", 150)
    data, centres = tiny_data()
    models = predict_demo.train_all(data, log=lambda s: None)
    assert list(models) == predict_demo.ORDER
    for cls_idx in (0, 3):
        res = predict_demo.predict_all(models, centres[cls_idx])
        assert set(res) == set(predict_demo.ORDER)
        assert res["logreg"]["label"] == config.CLASSES[cls_idx]
        assert res["logreg"]["kind"] == "probability" and 0 < res["logreg"]["score"] <= 1
        assert res["linearsvc"]["label"] == config.CLASSES[cls_idx]
        assert all(r["label"] in config.CLASSES and r["runner_up"] != r["label"] for r in res.values())


def test_pipeline_exposes_scores_and_classes(monkeypatch):
    monkeypatch.setitem(predict_demo.svm_classify.SCRATCH, "epochs", 50)
    data, centres = tiny_data(1)
    p = predict_demo.svm_classify.make_model("svm_scratch").fit(data["X_pool"], data["y_pool"])
    assert isinstance(p, Pipeline) and list(p.classes_) == sorted(config.CLASSES)
    assert p.decision_function(centres[:1].astype(np.float32)).shape == (1, 6)


class FakeEncoder:
    max_seq_length = 256

    def encode(self, texts, batch_size, normalize_embeddings, show_progress_bar, convert_to_numpy):
        v = np.ones((len(texts), 4)); return v / np.linalg.norm(v, axis=1, keepdims=True)


def test_embed_article_uses_title_and_truncates_lead():
    vec = predict_demo.embed_article(FakeEncoder(), "Title", "word " * 5000)
    assert vec.shape == (4,) and vec.dtype == np.float32


def test_show_marks_right_and_wrong(capsys):
    res = {n: {"label": "technology" if n != "svm_poly" else "other", "score": 0.9, "runner_up": "politics",
               "scores": {"technology": 0.9, "other": 0.5, "politics": 0.1},
               "runner_up_score": 0.1, "kind": "probability" if n == "logreg" else "margin"}
           for n in predict_demo.ORDER}
    predict_demo.show(res, "T", truth="technology")
    out = capsys.readouterr().out
    assert out.count("OK") == 3 and out.count("WRONG") == 1


def _res(labels, runners=None, logreg_probs=None):
    runners = runners or ["technology"] * 4
    out = {}
    for n, lab, ru in zip(predict_demo.ORDER, labels, runners):
        out[n] = {"label": lab, "score": 0.9, "scores": {lab: 0.9, ru: 0.1}, "runner_up": ru,
                  "runner_up_score": 0.1, "kind": "probability" if n == "logreg" else "margin"}
    if logreg_probs:
        out["logreg"]["scores"] = logreg_probs
    return out


def test_verdict_unanimous_majority_split():
    v = predict_demo.build_verdict(_res(["politics"] * 4))
    assert v["label"] == "politics" and v["agreement"] == "unanimous" and "confident" in v["summary"]
    v = predict_demo.build_verdict(_res(["politics", "politics", "politics", "other"]))
    assert v["label"] == "politics" and v["agreement"] == "majority"
    assert any("Others: other" in r for r in v["reasons"])
    v = predict_demo.build_verdict(_res(["politics", "other", "technology", "health"]))
    assert v["agreement"] == "split" and "UNCERTAIN" in v["summary"]


def test_verdict_tie_is_broken_by_logistic_regression():
    res = _res(["politics", "other", "politics", "other"],
               logreg_probs={"politics": 0.2, "other": 0.7})
    v = predict_demo.build_verdict(res)
    assert v["label"] == "other" and any("tied" in r for r in v["reasons"])


def test_verdict_uses_neighbours_and_has_reliability_note():
    neigh = [(0.8, "politics", "Title A", "a.com"), (0.7, "politics", "Title B", "b.com"),
             (0.6, "other", "Title C", "c.com")]
    v = predict_demo.build_verdict(_res(["politics"] * 4), neigh)
    assert v["neighbour_agree"] == 2
    assert any("closest articles" in r and "Title A" in r for r in v["reasons"])
    assert "80%" in v["reasons"][-1]


def test_find_and_describe_neighbours():
    ids = np.array([10, 20, 30]); mat = np.array([[1, 0], [0, 1], [0.9, 0.1]], dtype=np.float32)
    found = predict_demo.find_neighbours(np.array([1, 0], dtype=np.float32), ids, mat, k=2)
    assert [i for _, i in found] == [10, 30]
    d = predict_demo.describe_neighbours(found, {10: "politics"}, {10: ("T", "a.com")})
    assert d[0][1:] == ("politics", "T", "a.com") and d[1][1] == "?" and d[1][2] == "(title not available)"


def test_show_prints_final_result(capsys):
    res = _res(["technology"] * 4)
    predict_demo.show(res, "T", truth="technology")
    out = capsys.readouterr().out
    assert "FINAL RESULT: technology" in out and "RIGHT" in out and "Reasons:" in out
