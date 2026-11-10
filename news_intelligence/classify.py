"""Phase 5: can a classifier on the saved vectors recover the topic, judged ONLY by hand labels?

Training labels come from the rule classifier (articles it was confident about). The test is your
hand-labelled articles, which are never used for training. Two schemes:
  seen websites    train on every training article except the hand-labelled ones
  unseen websites  for each test fold, also remove every training article from the fold's websites
Baselines on the same hand-labelled articles: always `other`, the website's most common rule label,
and the rule classifier itself ('uncertain' counts as wrong).

    python classify.py
"""
import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict

import numpy as np

import config
import embeddings
import evaluate
import similarity

C_VALUE = 10.0                          # fixed in advance, not tuned on the hand labels


def read_columns(path, columns):
    """{column: [values...]} for the named columns of a CSV (utf-8 with or without BOM)."""
    csv.field_size_limit(2 ** 31 - 1)
    out = {c: [] for c in columns}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = [c for c in columns if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing columns {missing}; found {reader.fieldnames}")
        for row in reader:
            for c in columns:
                out[c].append(row[c])
    return out


def read_id_list(path):
    return {int(v) for v in read_columns(path, ["id"])["id"]}


def mcnemar_exact(b, c):
    """Two-sided exact p-value for 'A right, B wrong' (b) versus 'A wrong, B right' (c)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def domain_majority(domains, labels):
    """Most common label per website."""
    votes = defaultdict(Counter)
    for d, l in zip(domains, labels):
        votes[d][l] += 1
    return {d: c.most_common(1)[0][0] for d, c in votes.items()}


def train_predict(Xtr, ytr, Xte, seed=config.SEED):
    from sklearn.linear_model import LogisticRegression
    clf = LogisticRegression(C=C_VALUE, max_iter=1000, class_weight="balanced", random_state=seed)
    clf.fit(Xtr, ytr)
    return list(clf.predict(Xte))


def head_to_head(truth, pred_a, pred_b):
    """Counts of who is right when two predictors disagree about hand-labelled articles."""
    both = a_only = b_only = neither = 0
    for t, a, b in zip(truth, pred_a, pred_b):
        ra, rb = a == t, b == t
        both += ra and rb
        a_only += ra and not rb
        b_only += rb and not ra
        neither += not ra and not rb
    return {"both_right": both, "classifier_only_right": a_only, "rules_only_right": b_only,
            "both_wrong": neither, "exact_p_value": round(mcnemar_exact(a_only, b_only), 4)}


def run_schemes(X_pool, y_pool, dom_pool, X_test, y_test, dom_test, n_splits=5, log=print):
    """Predictions for the test articles under both schemes."""
    from sklearn.model_selection import GroupKFold
    log(f"seen websites: training on {len(y_pool):,} articles ...")
    seen = train_predict(X_pool, y_pool, X_test)
    unseen = np.empty(len(y_test), dtype=object)
    dom_pool = np.asarray(dom_pool)
    y_pool = np.asarray(y_pool)
    for n, (_, test_idx) in enumerate(GroupKFold(n_splits=n_splits).split(X_test, y_test, dom_test), 1):
        banned = set(np.asarray(dom_test)[test_idx])
        keep = ~np.isin(dom_pool, list(banned))
        log(f"unseen websites, fold {n}/{n_splits}: {len(banned)} websites removed, "
            f"training on {int(keep.sum()):,} articles ...")
        unseen[test_idx] = train_predict(X_pool[keep], y_pool[keep], X_test[test_idx])
    return seen, list(unseen)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    try:
        ids, mat = embeddings.load_embeddings(similarity.default_embeddings_dir())
        row_of = {int(a): i for i, a in enumerate(ids)}
        labels, lab_report = evaluate.load_labels([config.LABELS_DIR / "my_labels.csv",
                                                   config.LABELS_DIR / "my_labels_round2.csv"])
        boiler_path = config.ARTIFACTS_DIR / "boilerplate_ids.csv"
        if not boiler_path.exists():
            raise FileNotFoundError(f"{boiler_path} not found. Run boilerplate.py first.")
        boiler = read_id_list(boiler_path)
        cand = read_columns(config.LABELS_DIR / "ml_training_candidates.csv", ["id", "domain", "category"])
        rules = read_columns(config.LABELS_DIR / "articles_classified.csv", ["id", "domain", "category"])
    except (config.ConfigError, FileNotFoundError, ValueError) as exc:
        print("PROBLEM:", exc)
        return 1

    rule_of = {int(i): c for i, c in zip(rules["id"], rules["category"])}
    dom_of = {int(i): d for i, d in zip(rules["id"], rules["domain"])}
    pool = [(int(i), d, c) for i, d, c in zip(cand["id"], cand["domain"], cand["category"])
            if c in config.CLASSES and int(i) not in labels and int(i) not in boiler and int(i) in row_of]
    test_ids = sorted(a for a in labels if a in row_of and a in rule_of)
    p_ids, p_dom, p_lab = zip(*pool)
    X_pool = mat[[row_of[i] for i in p_ids]]
    X_test = mat[[row_of[i] for i in test_ids]]
    y_test = [labels[i] for i in test_ids]
    d_test = [dom_of[i] for i in test_ids]

    seen, unseen = run_schemes(X_pool, list(p_lab), p_dom, X_test, y_test, d_test)
    rule_pred = [rule_of[i] for i in test_ids]
    dmaj = domain_majority(p_dom, p_lab)
    dom_pred = [dmaj.get(d, "other") for d in d_test]

    out = {"hand_labels": lab_report, "test_articles": len(test_ids),
           "training_articles": len(pool),
           "training_class_counts": dict(Counter(p_lab)),
           "excluded_from_training": {"hand_labelled": len(labels), "boilerplate_flagged": len(boiler)},
           "classifier_seen_websites": evaluate.score(y_test, seen),
           "classifier_unseen_websites": evaluate.score(y_test, unseen),
           "baseline_always_other": evaluate.majority_baseline(y_test),
           "baseline_website_majority_rule_label": evaluate.score(y_test, dom_pred),
           "rule_classifier": {**evaluate.score(y_test, rule_pred),
                               "rule_said_uncertain": sum(r == "uncertain" for r in rule_pred)},
           "head_to_head_seen_vs_rules": head_to_head(y_test, seen, rule_pred),
           "head_to_head_unseen_vs_rules": head_to_head(y_test, unseen, rule_pred)}
    config.ARTIFACTS_DIR.mkdir(exist_ok=True)
    (config.ARTIFACTS_DIR / "phase5_results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    with open(config.ARTIFACTS_DIR / "phase5_predictions.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "hand_label", "classifier_seen", "classifier_unseen", "rule_label"])
        w.writerows(zip(test_ids, y_test, seen, unseen, rule_pred))
    for k in ("classifier_seen_websites", "classifier_unseen_websites", "baseline_website_majority_rule_label",
              "rule_classifier"):
        out[k] = {x: v for x, v in out[k].items() if x != "per_class"} | \
                 {"per_class_recall": {c: (v["recall"] if v["n"] else None) for c, v in out[k]["per_class"].items()}
                  if "per_class" in out[k] else None}
    print(json.dumps(out, indent=2))
    print(f"(saved phase5_results.json and phase5_predictions.csv in {config.ARTIFACTS_DIR})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
