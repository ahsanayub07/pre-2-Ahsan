"""Phase 4d: how many articles start with repeated page furniture (paywall prompts, sign-up
forms, site blurbs) instead of article text? Read-only; changes nothing.

    python boilerplate.py                       scan all ML-ready articles
    python boilerplate.py --min-count 3 --prefix-chars 100

An article is a *candidate* when the first N characters of its body (whitespace and case
normalised) are identical to those of at least `min_count` articles on the SAME website.
Candidates are not proof: templated but genuine articles can look the same. Look at the examples.
"""
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict

import config
import data_access
import evaluate


def prefix_key(lead, n):
    """First n characters of the lead, lower-cased and with whitespace collapsed ('' if too short)."""
    text = " ".join((lead or "").lower().split())
    return text[:n] if len(text) >= n else ""


def find_boilerplate(articles, prefix_chars=150, min_count=5):
    """Group articles by (website, opening text). Returns {(domain, prefix): [article ids]} for
    groups with at least min_count members."""
    groups = defaultdict(list)
    for a in articles:
        key = prefix_key(a.lead, prefix_chars)
        if key:
            groups[(a.domain, key)].append(a.id)
    return {k: v for k, v in groups.items() if len(v) >= min_count}


def summarize(groups, total, label_ids=(), top=15):
    affected = {i for ids in groups.values() for i in ids}
    by_domain = Counter()
    for (domain, _), ids in groups.items():
        by_domain[domain] += len(ids)
    ranked = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    label_ids = set(label_ids)
    return {"articles_scanned": total, "repeated_opening_groups": len(groups),
            "articles_affected": len(affected),
            "share_affected": round(len(affected) / total, 4) if total else 0.0,
            "affected_in_hand_labels": len(affected & label_ids),
            "hand_labels_checked": len(label_ids),
            "top_websites": by_domain.most_common(10),
            "top_repeated_openings": [{"articles": len(ids), "website": d, "opening": p[:100]}
                                      for (d, p), ids in ranked[:top]]}, sorted(affected)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--prefix-chars", type=int, default=150)
    ap.add_argument("--min-count", type=int, default=5)
    args = ap.parse_args(argv)
    try:
        ids = data_access.load_ml_ready_ids()
        conn = data_access.get_readonly_connection()
        try:
            arts = list(data_access.fetch_articles(conn, ids, lead_chars=max(300, args.prefix_chars * 2)))
        finally:
            conn.close()
        try:
            labels, _ = evaluate.load_labels([config.LABELS_DIR / "my_labels.csv",
                                              config.LABELS_DIR / "my_labels_round2.csv"])
        except FileNotFoundError:
            labels = {}
        groups = find_boilerplate(arts, args.prefix_chars, args.min_count)
        rep, affected = summarize(groups, len(arts), labels)
    except (config.ConfigError, FileNotFoundError, ValueError) as exc:
        print("PROBLEM:", exc)
        return 1
    config.ARTIFACTS_DIR.mkdir(exist_ok=True)
    (config.ARTIFACTS_DIR / "phase4d_boilerplate.json").write_text(
        json.dumps({**rep, "settings": vars(args)}, indent=2), encoding="utf-8")
    with open(config.ARTIFACTS_DIR / "boilerplate_ids.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["id"]); w.writerows([i] for i in affected)
    print(json.dumps(rep, indent=2))
    print(f"(saved phase4d_boilerplate.json and boilerplate_ids.csv in {config.ARTIFACTS_DIR})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
