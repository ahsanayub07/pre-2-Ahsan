"""Phase 3b: which encoder setup separates the topics best? Uses ONLY the hand-labelled articles.

For each setup: embed the labelled articles, train a simple classifier (logistic regression),
and score it on articles from websites it did NOT train on (grouped 5-fold). Also runs a
shuffled-label control: it must score near chance, otherwise the test itself is broken.

    python compare_models.py
    python compare_models.py --config sentence-transformers/all-MiniLM-L6-v2:256 --config bert-base-uncased:512
"""
import argparse
import json
import random
import sys

import numpy as np

import config
import data_access
import embeddings
import evaluate
from text_prep import build_model_text

DEFAULT_CONFIGS = ["sentence-transformers/all-MiniLM-L6-v2:256",
                   "sentence-transformers/all-MiniLM-L6-v2:512",
                   "bert-base-uncased:512"]
C_VALUE = 10.0                      # fixed in advance, not tuned on the labels


def cross_validated_predictions(X, y, groups, n_splits=5, seed=config.SEED):
    """Out-of-fold predictions; every article is predicted by a model that never saw its website."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupKFold
    y = np.asarray(y)
    pred = np.empty(len(y), dtype=object)
    for train, test in GroupKFold(n_splits=n_splits).split(X, y, groups):
        if len(set(y[train])) < 2:
            pred[test] = y[train][0]
            continue
        clf = LogisticRegression(C=C_VALUE, max_iter=2000, class_weight="balanced",
                                 random_state=seed)
        clf.fit(X[train], y[train])
        pred[test] = clf.predict(X[test])
    return list(pred)


def evaluate_setup(X, y, groups, seed=config.SEED):
    pred = cross_validated_predictions(X, y, groups)
    result = evaluate.score(list(y), pred)
    shuffled = list(y)
    random.Random(seed).shuffle(shuffled)
    ctrl = evaluate.score(shuffled, cross_validated_predictions(X, shuffled, groups))
    result["shuffled_label_control_accuracy"] = ctrl["accuracy"]
    return result


def parse_config(text):
    name, _, length = text.rpartition(":")
    if not name or not length.isdigit():
        raise ValueError(f"--config must look like model:length, got {text!r}")
    return name, int(length)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--config", action="append", help="model:max_seq_length (repeatable)")
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--labels", nargs="*", default=None, help="label CSV files")
    args = p.parse_args(argv)
    try:
        paths = args.labels or [config.LABELS_DIR / "my_labels.csv",
                                config.LABELS_DIR / "my_labels_round2.csv"]
        labels, report = evaluate.load_labels(paths)
        ids = sorted(labels)
        conn = data_access.get_readonly_connection()
        try:
            arts = list(data_access.fetch_articles(conn, ids))
        finally:
            conn.close()
        found = {a.id for a in arts}
        if len(found) != len(ids):
            print(f"note: {len(ids) - len(found)} labelled ids not found in the table")
        y = [labels[a.id] for a in arts]
        groups = [a.domain for a in arts]
        texts = [build_model_text(a.title, a.lead) for a in arts]
        out = {"labels": report, "n_articles": len(arts), "distinct_domains": len(set(groups)),
               "class_counts": {c: y.count(c) for c in config.CLASSES},
               "majority_baseline": evaluate.majority_baseline(y), "setups": {}}
        for text in args.config or DEFAULT_CONFIGS:
            name, length = parse_config(text)
            print(f"embedding {len(texts)} labelled articles with {name} (length {length}) ...")
            enc = embeddings.load_encoder(name, length)
            X = embeddings.encode(enc, texts, args.batch_size)
            res = evaluate_setup(X, y, groups)
            res["max_seq_length"] = enc.max_seq_length
            out["setups"][f"{name}:{length}"] = res
            print(f"  accuracy {res['accuracy']} {res['accuracy_95_range']}, "
                  f"macro-F1 {res['macro_f1']}, shuffled control {res['shuffled_label_control_accuracy']}")
        config.ARTIFACTS_DIR.mkdir(exist_ok=True)
        path = config.ARTIFACTS_DIR / "compare_models.json"
        path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    except (config.ConfigError, FileNotFoundError, ValueError, ImportError) as exc:
        print("PROBLEM:", exc)
        return 1
    print(json.dumps(out, indent=2))
    print(f"(saved to {path})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
