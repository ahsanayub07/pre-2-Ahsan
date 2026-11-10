# News Intelligence: applying Transformer encoders to the news dataset

All numbers below are from real runs on the project owner's PC (Windows 10, 4 CPU threads, no GPU,
8.2 GB RAM). Each is logged in `reports/experiments.md`. Nothing was estimated from a paper.

## 1. Summary
A pretrained Transformer encoder (`all-MiniLM-L6-v2`) turned all 95,094 ML-ready articles into
384-number vectors. A simple classifier on those vectors, trained on rule labels, reached
**80.6% accuracy on 293 hand-labelled articles** (95% range 75.6 to 84.7), against 72.4% for the
rule classifier and 34.8% for always answering `other`. An SVM (the company notebook's algorithm, ported and extended to six classes) scored 79.9%, the same as logistic regression within noise. Similar-article search works. A scan found
that at least 2.35% of articles start with repeated page furniture instead of article text.

## 2. The paper and how it is used
"Attention Is All You Need" (Vaswani et al., 2017) introduces the Transformer: self-attention,
`softmax(QK^T / sqrt(d_k)) V`, multi-head attention (8 heads, d_k = d_v = 64, d_model = 512), an
encoder and decoder of 6 layers each, a feed-forward size of 2048, and sinusoidal positional
encoding. The base model has about 65M parameters and was trained for 12 hours on 8 GPUs. The paper
tests translation and parsing only; it says nothing about news.

This project uses the **encoder half**, already trained by others (BERT family). Nothing was trained
from scratch: that needs far more data and compute than this PC has. The encoder is frozen; only a
small classifier is trained on top.

## 3. What was built (`news_intelligence/`)
| File | Purpose |
|---|---|
| `config.py`, `data_access.py`, `text_prep.py` | Settings, read-only database access, text preparation |
| `explore.py` | Hardware, database counts, text lengths |
| `embeddings.py` | Embeds articles in resumable shards |
| `compare_models.py`, `evaluate.py` | Compares encoder setups on the hand labels; metrics with Wilson ranges |
| `similarity.py` | Verification, nearest neighbours, duplicate tests, `--show`, `--peek` |
| `boilerplate.py` | Finds repeated page furniture |
| `classify.py` | Logistic regression scored on hand labels |
| `svm_model.py`, `svm_classify.py` | SVM from the company notebook (hinge loss, gradient descent), one-vs-rest, plus LinearSVC and a polynomial variant |
| `tests/` | 53 tests, no database or download needed (4 more optional database tests) |

`public.articles_cleaned` is only read, through a read-only connection. Nothing is written to the database.

## 4. Results
| Step | Result |
|---|---|
| Database | Counts match the documented 100,026 / 100,026 / 95,094 |
| Text length | Median 337 tokens; 90.1% of articles exceed the 256-token limit; p99 is 496 |
| Speed (1,000 articles) | MiniLM at 256: 9.2 articles/s; at 512: 5.95/s; plain BERT at 512 (100 articles): 1.37/s |
| Full embedding run | 95,094 articles in 7,503 s (about 2.1 h), 12.67 articles/s, peak 0.71 GB |
| Encoder comparison (293 labels, grouped 5-fold) | MiniLM-256 69.6%, MiniLM-512 70.0%, BERT-512 73.0%; differences within noise |
| Similarity | Median closest-neighbour similarity 0.70; spot checks give sensible neighbours |
| Duplicate test | Original found at rank 1 / 5 / 10 for 65.9% / 75.3% / 78.9% of 748 known later copies |
| Boilerplate scan | 2,235 articles (2.35%) start with text repeated across at least 5 articles on one website |
| **Classifier** | **80.6% (75.6 to 84.7), macro-F1 0.750, on seen and unseen websites** |
| **SVM (notebook algorithm), seen websites** | **79.9% (74.9 to 84.1), macro-F1 0.755** |
| LinearSVC (scikit-learn) seen / unseen websites | 79.5% / 79.9%, macro-F1 0.762 / 0.753 |
| Polynomial SVM (PCA 20 + degree 2) | 78.5% (73.4 to 82.8), macro-F1 0.691 |
| SVM against logistic regression | Articles only one is right on: 12 against 14 (p = 0.85). No difference |
| Rule classifier, same articles | 72.4% (67.0 to 77.2), macro-F1 0.717 (29 `uncertain` counted wrong) |
| Head-to-head | Classifier only right 43, rules only right 19, exact p = 0.0032 |

## 5. Findings
1. **Plain BERT is too slow here.** About 19 hours projected for all articles (not run), for a gain
   that could not be told apart from noise.
2. **Reading 512 words instead of 256 did not help** MiniLM on the hand labels.
3. **The duplicate test was misleading.** Of the known "duplicates", many have identical body text
   but unrelated headlines, because the scraper saved page furniture (paywall prompts, sign-up
   forms, site blurbs) as the body. The embeddings were correct; the pairs were not true duplicates.
4. **Boilerplate is partly junk, partly template.** News24, Independent, InfoQ and CNBC repeat
   navigation or paywall text; CNET puzzle hints and Forbes betting picks are templated but real.
5. **Training on many noisy rule labels beat training on few clean hand labels** (80.6% against 69.6%).
6. **The classifier's biggest gain over the rules is `market_stocks`** (recall 0.70 against 0.33).
7. **The classifier type matters little.** Logistic regression and SVMs all land at 79 to 81%; the gain over the rules comes from the embeddings and the amount of training data.
8. **The from-scratch SVM matches scikit-learn's** (234 and 233 of 293 correct), which supports the port of the notebook algorithm. Its training loss flattened by epoch 750 to 1000.

## 6. Limits
- The test set is 293 articles. Differences of a few points are noise. `energy` has 5 labels and `health` 11.
- The 100 round-2 labels were made by an assistant and were not spot-checked.
- Training labels come from keyword rules, so the model partly inherits their mistakes.
- The boilerplate scan sees only identical openings, so 2.35% is probably a minimum. The flagged
  articles were left out of training but stayed in the search index.
- Same-story leakage between training and test (the same story on another website) was not checked.
- The scrape is uneven in time (65,322 of 95,094 articles are from 2026).
- Model size and the 256-token limit come from third-party pages; the 90.9 MB download was observed.
- SVM settings (C = 1, learning rate 0.01, 1,000 epochs) were fixed in advance and not tuned. The polynomial SVM reduces the vectors to 20 numbers first, so it does not isolate the effect of curved boundaries. The notebook-style SVM was not run on unseen websites.
- One run per setup, no repeated seeds. The classifier setting `C = 10` was fixed in advance.

## 7. Decisions
- **Summarisation was not done.** A decoder or encoder-decoder model large enough to summarise well
  does not run comfortably on 8 GB RAM and a CPU, and the task did not require it.
- **No model was trained from scratch**, for the reason in section 2.

## 8. How to rerun (PowerShell, venv active, inside `news_intelligence`)
```powershell
pip install -r requirements.txt
python -m pytest -q
python explore.py --env ; python explore.py --counts ; python explore.py --lengths 2000
python embeddings.py --full --batch-size 8 --max-seq-length 256
python similarity.py --verify ; python similarity.py --build ; python similarity.py --dup-test
python boilerplate.py
python compare_models.py
python classify.py
python svm_classify.py --poly
```
Requires a `.env` with the database settings (copy `.env.example`; never commit it).

## 9. Next step
Optional: tune the SVM's C and learning rate on a held-out slice of the training articles (never on the hand labels), run the notebook SVM on unseen websites (`python svm_classify.py --scratch-unseen`), and label more `energy` and `health` articles so those classes can be judged.

Source: Vaswani et al., "Attention Is All You Need", 2017.
