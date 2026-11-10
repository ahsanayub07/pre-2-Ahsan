"""Phase 6: SVM on the saved vectors, judged ONLY by the hand labels (same test as classify.py).

Models
  svm_scratch     the company-notebook SVM (hinge loss + gradient descent), one-vs-rest, linear
  linearsvc       scikit-learn LinearSVC, a trusted reference for the same idea
  svm_poly        optional (--poly): PCA to 20 numbers, then degree-2 polynomial features, then the
                  notebook SVM (their polynomial trick; degree 2 on all 384 numbers is far too big)
Schemes: 'seen' websites (train on every training article except hand-labelled ones) and 'unseen'
websites (5 folds, the test fold's websites removed from training). The notebook SVM runs 'unseen'
only with --scratch-unseen because it is slow.

    python svm_classify.py
    python svm_classify.py --poly --scratch-unseen
"""
import argparse
import csv
import json
import sys
import time
from collections import Counter

import numpy as np

import classify
import config
import embeddings
import evaluate
import similarity
from svm_model import OneVsRestSVM, Pipeline

SCRATCH = {"learning_rate": 0.01, "epochs": 1000, "C": 1.0, "balanced": True, "seed": config.SEED}
# fixed in advance (not tuned on the hand labels)


def make_model(name):
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import PolynomialFeatures, StandardScaler
    if name == "svm_scratch":
        return Pipeline(StandardScaler(), OneVsRestSVM(verbose=True, **SCRATCH))
    if name == "linearsvc":
        from sklearn.svm import LinearSVC
        return Pipeline(StandardScaler(), LinearSVC(C=1.0, class_weight="balanced", dual=False,
                                                         max_iter=2000, random_state=config.SEED))
    if name == "svm_poly":
        return Pipeline(PCA(n_components=20, random_state=config.SEED),
                             PolynomialFeatures(degree=2, include_bias=False), StandardScaler(),
                             OneVsRestSVM(verbose=True, **SCRATCH))
    raise ValueError(name)


def fit_predict(name, Xtr, ytr, Xte):
    model = make_model(name)
    t0 = time.perf_counter()
    model.fit(Xtr, ytr)
    return [str(p) for p in model.predict(Xte)], model, round(time.perf_counter() - t0, 1)


def run_model(name, X_pool, y_pool, dom_pool, X_test, y_test, dom_test, do_unseen, log=print):
    from sklearn.model_selection import GroupKFold
    res = {}
    log(f"[{name}] seen websites: training on {len(y_pool):,} articles ...")
    seen, model, secs = fit_predict(name, X_pool, y_pool, X_test)
    res["seconds_seen_fit"] = secs
    res["seen"] = seen
    final = model.steps[-1][1]
    if hasattr(final, "models_"):
        res["final_loss_per_class"] = {c: round(m.final_loss, 4) for c, m in zip(final.classes_, final.models_)}
    sample = np.random.default_rng(config.SEED).choice(len(y_pool), size=min(5000, len(y_pool)), replace=False)
    res["train_accuracy_5000_sample"] = round(float(np.mean(
        np.array(model.predict(X_pool[sample])) == np.array(y_pool)[sample])), 4)
    if do_unseen:
        dom_pool, y_arr = np.asarray(dom_pool), np.asarray(y_pool)
        unseen = np.empty(len(y_test), dtype=object)
        for n, (_, idx) in enumerate(GroupKFold(n_splits=5).split(X_test, y_test, dom_test), 1):
            keep = ~np.isin(dom_pool, list(set(np.asarray(dom_test)[idx])))
            log(f"[{name}] unseen websites, fold {n}/5: training on {int(keep.sum()):,} articles ...")
            unseen[idx] = fit_predict(name, X_pool[keep], y_arr[keep], X_test[idx])[0]
        res["unseen"] = list(unseen)
    return res


def load_data():
    ids, mat = embeddings.load_embeddings(similarity.default_embeddings_dir())
    row_of = {int(a): i for i, a in enumerate(ids)}
    labels, _ = evaluate.load_labels([config.LABELS_DIR / "my_labels.csv",
                                      config.LABELS_DIR / "my_labels_round2.csv"])
    boiler_path = config.ARTIFACTS_DIR / "boilerplate_ids.csv"
    if not boiler_path.exists():
        raise FileNotFoundError(f"{boiler_path} not found. Run boilerplate.py first.")
    boiler = classify.read_id_list(boiler_path)
    cand = classify.read_columns(config.LABELS_DIR / "ml_training_candidates.csv", ["id", "domain", "category"])
    rules = classify.read_columns(config.LABELS_DIR / "articles_classified.csv", ["id", "domain", "category"])
    rule_of = {int(i): c for i, c in zip(rules["id"], rules["category"])}
    dom_of = {int(i): d for i, d in zip(rules["id"], rules["domain"])}
    pool = [(int(i), d, c) for i, d, c in zip(cand["id"], cand["domain"], cand["category"])
            if c in config.CLASSES and int(i) not in labels and int(i) not in boiler and int(i) in row_of]
    test_ids = sorted(a for a in labels if a in row_of and a in rule_of)
    p_ids, p_dom, p_lab = zip(*pool)
    return {"X_pool": mat[[row_of[i] for i in p_ids]], "y_pool": list(p_lab), "dom_pool": list(p_dom),
            "X_test": mat[[row_of[i] for i in test_ids]], "test_ids": test_ids,
            "y_test": [labels[i] for i in test_ids], "dom_test": [dom_of[i] for i in test_ids],
            "rule_pred": [rule_of[i] for i in test_ids], "n_boiler": len(boiler), "n_hand": len(labels)}


def read_lr_predictions(test_ids):
    """Logistic-regression predictions from Phase 5, if that file is present and matches."""
    path = config.ARTIFACTS_DIR / "phase5_predictions.csv"
    if not path.exists():
        return None
    cols = classify.read_columns(path, ["id", "classifier_seen", "classifier_unseen"])
    got = {int(i): (s, u) for i, s, u in zip(cols["id"], cols["classifier_seen"], cols["classifier_unseen"])}
    if any(i not in got for i in test_ids):
        return None
    return [got[i][0] for i in test_ids], [got[i][1] for i in test_ids]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--poly", action="store_true", help="also run the polynomial (PCA + degree 2) SVM")
    ap.add_argument("--scratch-unseen", action="store_true", help="also run the slow 'unseen websites' scheme for the notebook SVM")
    args = ap.parse_args(argv)
    try:
        d = load_data()
    except (config.ConfigError, FileNotFoundError, ValueError) as exc:
        print("PROBLEM:", exc)
        return 1
    y_test, test_ids = d["y_test"], d["test_ids"]
    plan = [("linearsvc", True), ("svm_scratch", args.scratch_unseen)] + ([("svm_poly", False)] if args.poly else [])
    out = {"test_articles": len(y_test), "training_articles": len(d["y_pool"]),
           "training_class_counts": dict(Counter(d["y_pool"])), "settings": {"scratch_svm": SCRATCH},
           "rule_classifier": evaluate.score(y_test, d["rule_pred"]), "models": {}}
    lr = read_lr_predictions(test_ids)
    preds = {"id": test_ids, "hand_label": y_test, "rule_label": d["rule_pred"]}
    if lr:
        preds["logreg_seen"], preds["logreg_unseen"] = lr
        out["logistic_regression_seen"] = evaluate.score(y_test, lr[0])
    for name, unseen in plan:
        r = run_model(name, d["X_pool"], d["y_pool"], d["dom_pool"], d["X_test"], y_test, d["dom_test"], unseen)
        entry = {k: v for k, v in r.items() if k not in ("seen", "unseen")}
        entry["seen_websites"] = evaluate.score(y_test, r["seen"])
        entry["head_to_head_vs_rules"] = classify.head_to_head(y_test, r["seen"], d["rule_pred"])
        if lr:
            h = classify.head_to_head(y_test, r["seen"], lr[0])
            entry["head_to_head_vs_logreg"] = {"svm_only_right": h["classifier_only_right"],
                                              "logreg_only_right": h["rules_only_right"],
                                              "both_right": h["both_right"], "both_wrong": h["both_wrong"],
                                              "exact_p_value": h["exact_p_value"]}
        preds[f"{name}_seen"] = r["seen"]
        if "unseen" in r:
            entry["unseen_websites"] = evaluate.score(y_test, r["unseen"])
            preds[f"{name}_unseen"] = r["unseen"]
        out["models"][name] = entry
    config.ARTIFACTS_DIR.mkdir(exist_ok=True)
    (config.ARTIFACTS_DIR / "svm_results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    keys = list(preds)
    with open(config.ARTIFACTS_DIR / "svm_predictions.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(keys)
        w.writerows(zip(*[preds[k] for k in keys]))
    for m in out["models"].values():                       # shorter printout: drop per-class tables
        for k in ("seen_websites", "unseen_websites"):
            if k in m:
                m[k] = {x: v for x, v in m[k].items() if x != "per_class"} | \
                       {"per_class_recall": {c: (v["recall"] if v["n"] else None) for c, v in m[k]["per_class"].items()}}
    out["rule_classifier"] = {x: v for x, v in out["rule_classifier"].items() if x != "per_class"}
    out.pop("logistic_regression_seen", None) if not lr else out.update(
        {"logistic_regression_seen": {x: v for x, v in out["logistic_regression_seen"].items() if x != "per_class"}})
    print(json.dumps(out, indent=2))
    print(f"(saved svm_results.json and svm_predictions.csv in {config.ARTIFACTS_DIR})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
