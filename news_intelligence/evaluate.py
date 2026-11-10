"""Honest evaluation helpers: label loading, accuracy with Wilson ranges, per-class scores."""
import csv
import math
from collections import Counter

import config


def wilson(successes, n, z=1.96):
    """95% Wilson range for a proportion (same method as the data-analysis stage)."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


def load_labels(paths, classes=None):
    """Read label files (columns article_id, your_label). Returns (labels, report).

    Only labels inside `classes` are kept. An article labelled differently in two files is
    dropped (and counted); the same label twice is kept once.
    """
    classes = set(classes or config.CLASSES)
    seen, dropped = {}, Counter()
    for path in paths:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not {"article_id", "your_label"} <= set(reader.fieldnames or []):
                raise ValueError(f"{path}: need columns article_id and your_label, "
                                 f"found {reader.fieldnames}")
            for row in reader:
                aid, lab = int(row["article_id"]), row["your_label"].strip()
                if lab not in classes:
                    dropped[f"label_{lab}"] += 1
                elif aid in seen and seen[aid] != lab:
                    seen[aid] = None
                    dropped["conflict_between_files"] += 1
                elif aid not in seen:
                    seen[aid] = lab
    labels = {a: l for a, l in seen.items() if l is not None}
    return labels, {"kept": len(labels), "dropped": dict(dropped)}


def score(y_true, y_pred, classes=None):
    """Accuracy (+Wilson), macro-F1 over classes that occur, per-class precision/recall/F1/n."""
    classes = classes or config.CLASSES
    n = len(y_true)
    correct = sum(t == p for t, p in zip(y_true, y_pred))
    per, f1s = {}, []
    for c in classes:
        tp = sum(t == c and p == c for t, p in zip(y_true, y_pred))
        fp = sum(t != c and p == c for t, p in zip(y_true, y_pred))
        fn = sum(t == c and p != c for t, p in zip(y_true, y_pred))
        support = tp + fn
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / support if support else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per[c] = {"n": support, "precision": round(prec, 3), "recall": round(rec, 3),
                  "f1": round(f1, 3)}
        if support:
            f1s.append(f1)
    return {"n": n, "accuracy": round(correct / n, 4) if n else 0.0,
            "accuracy_95_range": wilson(correct, n),
            "macro_f1": round(sum(f1s) / len(f1s), 4) if f1s else 0.0, "per_class": per}


def majority_baseline(y_true):
    """Accuracy of always answering the most common class."""
    if not y_true:
        return {"class": None, "accuracy": 0.0}
    cls, cnt = Counter(y_true).most_common(1)[0]
    return {"class": cls, "accuracy": round(cnt / len(y_true), 4)}
