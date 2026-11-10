# Experiment log

Every entry is a **real run**: date, settings, command, and the numbers it printed. Nothing is
estimated or copied from a paper. Hardware for all runs: Windows 10, Python 3.14.7, 4 CPU threads,
no GPU, 8.2 GB RAM (about 1 GB free during the first checks).

| Date | Phase | What was run | Result | Where saved |
|---|---|---|---|---|
| 2026-11-09 | 2 | `explore.py --env` | 4 CPU threads, no GPU, 8.2 GB RAM, 42.5 GB disk free | artifacts/phase2_environment.json |
| 2026-11-09 | 2 | `explore.py --counts` | Live counts match the documented ones: 100,026 / 100,026 / 95,094; all ML-ready ids found in `articles_cleaned` | artifacts/phase2_counts.json |
| 2026-11-09 | 2 | `explore.py --lengths 2000` (seed 42) | 109 websites; 0 empty titles; 0 empty leads; tokens: median 337, p90 380, p99 496, max 1,206; 90.1% of articles exceed 256 tokens | artifacts/phase2_lengths.json |
| 2026-11-09 | 3 | pilot 1000, MiniLM-L6, 256 words, batch 8 | 9.2 articles/s; peak 0.60 GB | artifacts/embeddings/ |
| 2026-11-09 | 3 | pilot 1000, MiniLM-L6, 512 words, batch 8 | 5.95 articles/s; peak 0.65 GB | artifacts/embeddings/ |
| 2026-11-09 | 3 | pilot 100, bert-base-uncased, 512 words, batch 4 | 1.37 articles/s; peak 0.98 GB | artifacts/embeddings/ |
| 2026-11-09 | 3b | `compare_models.py`: 293 hand labels, domain-grouped 5-fold, logistic regression | MiniLM-256: 69.6% (64.1-74.6), macro-F1 0.617. MiniLM-512: 70.0% (64.5-74.9), 0.600. BERT-512: 73.0% (67.7-77.8), 0.655. Always-`other` baseline 34.8%. Shuffled-label control 22.5-25.9%. Differences between setups are within noise. | artifacts/compare_models.json |
| 2026-11-09 | 3c | `embeddings.py --full --batch-size 8 --max-seq-length 256` (MiniLM-L6) | 95,094 of 95,094 articles embedded in 7,503 s (about 2.08 h); 12.67 articles/s; peak 0.71 GB; 0 empty texts; 48 shards | artifacts/embeddings/full_sentence-transformers_all-MiniLM-L6-v2_len256 |
| 2026-11-09 | 4 | `similarity.py --verify` | ok: 95,094 rows x 384, all ids unique and matching the ML-ready list, unit length, no NaN, no all-zero rows | artifacts/phase4_verify.json |
| 2026-11-09 | 4 | `similarity.py --build` (k=10) | Top-1 similarity percentiles: p5 0.512, median 0.704, p95 0.915, p99 0.980. Closest neighbour at least 0.95 / 0.90 / 0.80: 2.8% / 6.5% / 25.8% | artifacts/phase4_neighbors_summary.json |
| 2026-11-09 | 4 | `similarity.py --dup-test` | 748 flagged later copies tested (31 skipped: original not in index). Original found at rank 1 / 5 / 10: 65.9% / 75.3% / 78.9%. Similarity to closest original: min 0.43, p10 0.65, median 0.96 | artifacts/phase4_duplicate_test.json |
| 2026-11-10 | 4b | `similarity.py --dup-diagnose` | 748 pairs: identical lead 100%, same title 31.6%, same website 98.4%. Lead-only similarity 1.0 for every pair. 295 pairs below 0.9 on title+lead, all with different titles. | artifacts/phase4b_duplicate_diagnosis.json |
| 2026-11-10 | 4c | `similarity.py --peek` on ids 38990, 44369, 6189 | The "bodies" are page furniture, not articles: a News24 subscriber-share prompt, a The Star promotion sign-up form, a 9to5Mac site blurb | (terminal output) |
| 2026-11-10 | 4d | `boilerplate.py` (150 characters, at least 5 articles on the same website) | 2,235 of 95,094 articles (2.35%) in 112 groups have a repeated opening; 12 of 293 hand labels affected. Top websites: newyorker.com 285, independent.co.uk 270, forbes.com 265, cnet.com 218, news24.com 216, vox.com 193, infoq.com 141 | artifacts/phase4d_boilerplate.json, artifacts/boilerplate_ids.csv |
| 2026-11-10 | 5 | `classify.py`: logistic regression on the saved vectors, trained on 69,692 rule-labelled articles (hand-labelled and boilerplate-flagged excluded), scored on 293 hand labels | Seen websites: 80.6% (75.6-84.7), macro-F1 0.750. Unseen websites (5 folds, test websites removed from training): 80.6% (75.6-84.7), macro-F1 0.750. Always-`other` 34.8%. Website-majority rule label 65.2% (59.6-70.4), F1 0.491. Rule classifier 72.4% (67.0-77.2), F1 0.717, with 29 `uncertain` counted wrong. Classifier-only right 43, rules-only right 19, exact p = 0.0032. | artifacts/phase5_results.json, artifacts/phase5_predictions.csv |
| 2026-11-10 | 6 | `svm_classify.py --poly`: SVM variants on the saved vectors, trained on 69,692 rule-labelled articles, scored on 293 hand labels | LinearSVC (scikit-learn): seen websites 79.5% (74.5-83.8), macro-F1 0.762; unseen websites 79.9% (74.9-84.1), F1 0.753. Notebook-style SVM (from scratch, one-vs-rest, C=1, learning rate 0.01, 1,000 epochs, balanced class weights): seen 79.9% (74.9-84.1), F1 0.755; fit 105 s; loss flat by epoch 750. Polynomial SVM (PCA to 20 numbers, degree 2): 78.5% (73.4-82.8), F1 0.691. Logistic regression (Phase 5): 80.6%. Rules: 72.4%. SVM vs logistic regression, articles only one is right on: scratch 12 vs 14 (p=0.85), LinearSVC 8 vs 11 (p=0.65), polynomial 15 vs 21 (p=0.41). SVM vs rules: p=0.009 (scratch), 0.011 (LinearSVC), 0.039 (polynomial). | artifacts/svm_results.json, artifacts/svm_predictions.csv |

## Notes
- The 100 round-2 hand labels were made by an assistant and have not been spot-checked.
- `energy` has only 5 hand labels and `health` 11, so their per-class scores are unstable.
- The plain BERT pilot used batch size 4 and only 100 articles; its 19-hour full-run figure is a projection and was never run.
- The 4d scan finds *candidates*. Some repeated openings are genuine templates (CNET daily puzzle hints, Forbes NFL picks, Vox newsletter intros), not junk. The scan only sees identical openings, so 2.35% is probably a minimum.
- The earlier 66% duplicate recall mostly reflects pairs that are not true duplicates (identical boilerplate, different headline), not an embedding failure.
- Phase 5: seen and unseen schemes both got 236 of 293 right; their per-class results differ slightly. Only 29 rule `uncertain` answers were counted wrong, which lowers the rule classifier's accuracy. `energy` (5 labels) and `health` (11) are too small to judge. Possible same-story leakage across websites was not checked.
- Phase 6: SVM settings (C, learning rate, epochs) were fixed in advance and not tuned. The notebook-style SVM and the polynomial SVM were not run on unseen websites. The polynomial SVM first reduces the vectors to 20 numbers, so its result mixes two effects (less information, more curvature).
