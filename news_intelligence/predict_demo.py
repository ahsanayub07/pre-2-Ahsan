"""Try the models on one article: train once, then predict any text with every model.

    python predict_demo.py --train                      train 4 models (several minutes), save them
    python predict_demo.py --sample technology          predict one of the built-in invented articles
    python predict_demo.py --title "..." --text "..."   predict your own article
    python predict_demo.py --file article.txt --title "..."

Models: logistic regression, LinearSVC, the notebook-style SVM, and the polynomial SVM.
The built-in samples are INVENTED for testing; they are not real news.
The scores are not accuracy: one article is one right or wrong answer. Accuracy is measured on
the 293 hand labels (see reports/FINAL_REPORT.md).
"""
import argparse
import pickle
import sys
import time

import numpy as np

import config
import embeddings
import svm_classify
from svm_model import Pipeline
from text_prep import build_model_text

MODEL_FILE = config.ARTIFACTS_DIR / "demo_models.pkl"
ORDER = ["logreg", "linearsvc", "svm_scratch", "svm_poly"]
LABELS = {"logreg": "Logistic regression", "linearsvc": "LinearSVC (scikit-learn)",
          "svm_scratch": "SVM from the notebook", "svm_poly": "Polynomial SVM"}

SAMPLES = {
    "technology": ("New open-source toolkit makes it easier to run language models on laptops",
                   "Developers released an open-source toolkit this week that lets language models run on "
                   "ordinary laptops without a graphics card. The software compresses model weights to a "
                   "fraction of their size and splits the work across processor cores. Early testers reported "
                   "that a small model answered questions in a few seconds on a four-core machine. The authors "
                   "said the goal is to let students and small companies experiment with artificial intelligence "
                   "without paying for cloud servers. The project is available on a public code repository and "
                   "comes with tutorials for beginners."),
    "health": ("Study links regular walking to lower blood pressure in older adults",
               "Researchers reported that adults over sixty who walked briskly for thirty minutes on most days "
               "had lower blood pressure after six months than a comparison group who did not change their "
               "routine. The trial followed several hundred volunteers at community clinics. Doctors not "
               "involved in the study said the result fits earlier evidence that moderate exercise helps the "
               "heart, and advised patients to talk to their physician before starting a new exercise plan. "
               "The authors called for larger studies to confirm the effect."),
    "market_stocks": ("Shares close higher as investors weigh interest rate outlook",
                      "Major stock indexes ended the session higher on Tuesday as investors weighed signs of "
                      "cooling inflation and the outlook for interest rates. Technology and bank shares led the "
                      "gains, while energy shares slipped. Bond yields edged lower and the dollar was little "
                      "changed. Traders said quarterly earnings reports due later this week would give a clearer "
                      "picture of company profits. Trading volume was close to its recent average."),
    "energy": ("Wind farm expansion expected to lift regional power supply next year",
               "A regional utility said a planned expansion of its offshore wind farm would add enough "
               "capacity to supply an extra two hundred thousand homes once it is connected to the grid next "
               "year. The company said turbine installation was ahead of schedule and that new transmission "
               "lines would carry the electricity to the coast. Officials said the project should reduce the "
               "region's reliance on natural gas during winter peaks, though they warned that grid upgrades "
               "remain costly."),
    "politics": ("Parliament debates new budget bill as opposition demands changes",
                 "Lawmakers began debating the government's budget bill on Monday, with opposition parties "
                 "demanding changes to tax proposals and spending on public services. The finance minister "
                 "defended the plan and said it would keep the deficit under control. Several members of the "
                 "ruling coalition indicated they might vote against parts of the bill unless amendments were "
                 "accepted. A final vote is expected at the end of the week."),
    "other": ("Local team wins youth football final in front of a record crowd",
              "A youth football team from the city won the regional final on Saturday after a late goal "
              "decided a close match. More than three thousand spectators filled the stadium, the largest "
              "crowd for a youth match in the region. The coach praised the players' discipline and said "
              "the club would use the prize money to repair its training pitch. Organisers thanked volunteers "
              "who helped run the event."),
}


def train_all(data, log=print):
    """Fit the four models on the training articles. Returns {name: model}."""
    from sklearn.linear_model import LogisticRegression
    X, y = data["X_pool"], data["y_pool"]
    models = {}
    for name in ORDER:
        log(f"training {LABELS[name]} on {len(y):,} articles ...")
        t0 = time.perf_counter()
        if name == "logreg":
            models[name] = LogisticRegression(C=10.0, max_iter=1000, class_weight="balanced",
                                              random_state=config.SEED).fit(X, y)
        else:
            models[name] = svm_classify.make_model(name).fit(X, y)
        log(f"  done in {time.perf_counter() - t0:.0f} s")
    return models


def predict_all(models, vector):
    """Every model's answer for one vector: label, a score and the runner-up label."""
    v = np.asarray(vector, dtype=np.float32).reshape(1, -1)
    out = {}
    for name in ORDER:
        m = models[name]
        scores = m.predict_proba(v)[0] if name == "logreg" else m.decision_function(v)
        scores = np.asarray(scores).reshape(-1)
        order = np.argsort(-scores)
        classes = list(m.classes_)
        out[name] = {"label": str(classes[order[0]]), "score": float(scores[order[0]]),
                     "scores": {str(c): float(x) for c, x in zip(classes, scores)},
                     "runner_up": str(classes[order[1]]), "runner_up_score": float(scores[order[1]]),
                     "kind": "probability" if name == "logreg" else "margin"}
    return out


def embed_article(encoder, title, text):
    t = build_model_text(title, " ".join((text or "").split())[:config.LEAD_CHARS])
    return embeddings.encode(encoder, [t], 1)[0]


def build_verdict(results, neighbours=None):
    """Combine the four answers into one final result with reasons.

    Rule: the category chosen by most models wins. On a tie, logistic regression's probabilities
    decide among the tied categories. 4 of 4 = unanimous, 3 of 4 = majority, fewer = split
    (reported as uncertain, for a person to review).
    neighbours: optional list of (similarity, rule_label, title, website) of the closest dataset articles.
    """
    from collections import Counter
    votes = Counter(results[n]["label"] for n in ORDER)
    top_count = max(votes.values())
    tied = [c for c, k in votes.items() if k == top_count]
    tie_note = None
    if len(tied) == 1:
        label = tied[0]
    else:
        probs = results["logreg"]["scores"]
        label = max(tied, key=lambda c: probs.get(c, 0.0))
        tie_note = (f"The models tied between {', '.join(sorted(tied))}; logistic regression's probabilities "
                    f"decided in favour of {label}.")
    agreement = {4: "unanimous", 3: "majority"}.get(top_count, "split")
    backers = [LABELS[n] for n in ORDER if results[n]["label"] == label]
    others = {c: [LABELS[n] for n in ORDER if results[n]["label"] == c] for c in votes if c != label}
    reasons = [f"{top_count} of 4 models chose {label} ({', '.join(backers)})."]
    if others:
        reasons[0] += " Others: " + "; ".join(f"{c} ({', '.join(m)})" for c, m in others.items()) + "."
    if tie_note:
        reasons.append(tie_note)
    runners = Counter(results[n]["runner_up"] for n in ORDER if results[n]["label"] == label)
    if runners:
        second, k = runners.most_common(1)[0]
        reasons.append(f"The next most likely topic is {second} (second choice of {k} of the {top_count} "
                       f"models that chose {label}), so the article has some overlap with {second}.")
    neighbour_agree = None
    if neighbours:
        counts = Counter(lab for _, lab, _, _ in neighbours)
        neighbour_agree = counts.get(label, 0)
        mix = ", ".join(f"{k} {c}" for c, k in counts.most_common())
        close = "; ".join(f'"{t[:70]}" [{w}] ({sim:.2f}, {lab})' for sim, lab, t, w in neighbours[:3])
        reasons.append(f"Of the {len(neighbours)} closest articles in your dataset, {neighbour_agree} are "
                       f"labelled {label} by the rules ({mix}). Closest three: {close}.")
    reasons.append("Reliability: on 293 hand-labelled test articles these models were right about 80% of the "
                   "time (79.5% to 80.6%). This is a prediction, not a certainty.")
    summary = {"unanimous": "confident (all 4 models agree)",
               "majority": "fairly confident (3 of 4 models agree)",
               "split": "UNCERTAIN: the models disagree, so a person should review it"}[agreement]
    return {"label": label, "agreement": agreement, "votes": dict(votes), "summary": summary,
            "reasons": reasons, "neighbour_agree": neighbour_agree}


def find_neighbours(vector, ids, mat, k=10):
    """The k dataset articles closest to the vector: [(similarity, article_id), ...]."""
    sims = mat @ np.asarray(vector, dtype=np.float32)
    top = np.argsort(-sims)[:k]
    return [(float(sims[i]), int(ids[i])) for i in top]


def describe_neighbours(found, rule_label_of, info_of):
    """Attach rule labels, titles and websites: [(similarity, label, title, website), ...]."""
    return [(sim, rule_label_of.get(i, "?"), info_of.get(i, ("(title not available)", "?"))[0],
             info_of.get(i, ("", "?"))[1]) for sim, i in found]


def show(results, title, truth=None, neighbours=None):
    print(f"\nArticle: {title}")
    if truth:
        print(f"True category (set by whoever wrote the sample): {truth}")
    print(f"\n{'Model':<28}{'Predicted':<16}{'Score':>9}   Runner-up")
    for name in ORDER:
        r = results[name]
        score = f"{r['score']:.2f}" if r["kind"] == "probability" else f"{r['score']:+.2f}"
        mark = "" if truth is None else ("  OK" if r["label"] == truth else "  WRONG")
        print(f"{LABELS[name]:<28}{r['label']:<16}{score:>9}   {r['runner_up']}{mark}")
    print("\nScore: a probability for logistic regression; a margin (distance from the boundary) for the SVMs. "
          "Neither is accuracy.")
    v = build_verdict(results, neighbours)
    print("\n" + "=" * 64)
    print(f"FINAL RESULT: {v['label']}   -   {v['summary']}")
    if truth:
        print(f"(True category set by the sample's author: {truth} -> {'RIGHT' if v['label'] == truth else 'WRONG'})")
    print("Reasons:")
    for n, r in enumerate(v["reasons"], 1):
        print(f"  {n}. {r}")
    print("=" * 64)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--sample", choices=sorted(SAMPLES))
    ap.add_argument("--all-samples", action="store_true", help="predict all six invented samples")
    ap.add_argument("--title", default="")
    ap.add_argument("--text")
    ap.add_argument("--file")
    ap.add_argument("--no-neighbours", action="store_true", help="skip the dataset look-up (faster, no database)")
    args = ap.parse_args(argv)
    if not (args.train or args.sample or args.all_samples or args.text or args.file):
        ap.print_help()
        return 0
    try:
        if args.train:
            models = train_all(svm_classify.load_data())
            config.ARTIFACTS_DIR.mkdir(exist_ok=True)
            with open(MODEL_FILE, "wb") as f:
                pickle.dump({"models": models, "trained_on": "rule labels, hand-labelled and boilerplate "
                             "articles excluded"}, f)
            print(f"models saved to {MODEL_FILE}")
            if not (args.sample or args.all_samples or args.text or args.file):
                return 0
        if not MODEL_FILE.exists():
            print("PROBLEM: no saved models. Run: python predict_demo.py --train")
            return 1
        models = pickle.load(open(MODEL_FILE, "rb"))["models"]
        encoder = embeddings.load_encoder(config.MODEL_NAME, config.MAX_SEQ_TOKENS)
        jobs = []
        if args.all_samples:
            jobs = [(t, x, c) for c, (t, x) in SAMPLES.items()]
        elif args.sample:
            t, x = SAMPLES[args.sample]
            jobs = [(t, x, args.sample)]
        else:
            text = open(args.file, encoding="utf-8").read() if args.file else args.text
            jobs = [(args.title, text, None)]
        index = rule_label_of = None
        if not args.no_neighbours:
            try:
                import classify
                import similarity
                index = embeddings.load_embeddings(similarity.default_embeddings_dir())
                cols = classify.read_columns(config.LABELS_DIR / "articles_classified.csv", ["id", "category"])
                rule_label_of = {int(i): c for i, c in zip(cols["id"], cols["category"])}
            except (FileNotFoundError, ValueError, ImportError) as exc:
                print(f"(dataset look-up skipped: {exc})")
        for title, text, truth in jobs:
            vec = embed_article(encoder, title, text)
            neigh = None
            if index is not None:
                found = find_neighbours(vec, index[0], index[1])
                info = {}
                try:
                    import data_access
                    conn = data_access.get_readonly_connection()
                    try:
                        info = {a.id: (a.title, a.domain) for a in
                                data_access.fetch_articles(conn, [i for _, i in found], lead_chars=1)}
                    finally:
                        conn.close()
                except (config.ConfigError, ImportError, Exception) as exc:   # database optional here
                    print(f"(titles of similar articles skipped: {str(exc)[:80]})")
                neigh = describe_neighbours(found, rule_label_of, info)
            show(predict_all(models, vec), title or "(no title)", truth, neigh)
    except (config.ConfigError, FileNotFoundError, ValueError, ImportError) as exc:
        print("PROBLEM:", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
