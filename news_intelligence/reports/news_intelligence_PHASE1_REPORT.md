# News Intelligence: Phase 1 Report (Research and Project Audit)

Date: 2026-11-08. Status: **Phase 1 only. Nothing has been created in your repository, no database was touched, and no model has been run.** Phase 2 starts only after you approve.

**How facts are marked in this report**

- **[Paper]** comes from the PDF you gave me (all 15 pages read).
- **[Repo]** comes from your repository and the documentation we built.
- **[Web]** comes from model web pages I fetched. Those pages are third-party copies of the model cards, so I treat them as "to be confirmed on download".
- **[My background knowledge]** is general machine-learning knowledge that is not in the paper or the repository. It is explained but must be tested in later phases.
- **[Not verified]** means I could not check it.

---

## 1. Research paper understanding

"Attention Is All You Need" (Vaswani et al., NIPS 2017) builds a translation model, the **Transformer**, that uses **only attention**. Earlier models (RNN, LSTM) read a sentence one word at a time, so they were slow to train and had trouble linking words that are far apart. The Transformer looks at **all words at once** and learns which words matter for which.

| Concept | What it really does (simple English) | Paper reference | Useful for news analysis? |
|---|---|---|---|
| **Attention** | For one word, compute how much every other word matters, then mix their information using those weights | Section 3.2 | Yes, this is the core idea |
| **Query, Key, Value (Q, K, V)** | Each word makes a *question* (Q), a *label* (K) and *content* (V). A word whose K matches your Q contributes its V | 3.2 | Yes (inside every pretrained model) |
| **Scaled dot-product attention** | `softmax(QKᵀ / √d_k) V` (Equation 1). Dividing by √d_k stops large numbers from making the softmax too extreme (footnote 4: dot products have variance d_k) | 3.2.1 | Yes |
| **Multi-head attention** | Run attention several times in parallel with different learned views (h = 8 heads, d_k = d_v = 64), then join the results. A single head averages everything together | 3.2.2 | Yes. Paper: one head is 0.9 BLEU worse than the best setting (Table 3 row A) |
| **Self-attention** | Q, K and V all come from the same sentence, so words attend to other words in the same text | 3.2.3 | **Most relevant**: understanding one article |
| **Encoder** | Stack of N = 6 layers; each has self-attention then a feed-forward network, with residual connections and layer normalisation | 3.1 | **Yes**: an encoder turns text into vectors |
| **Decoder** | Same, plus masked self-attention and attention over the encoder output; writes the output one word at a time | 3.1 | Only for summarisation or generation, not for classification or similarity |
| **Feed-forward network** | Two linear layers with ReLU, applied to each position separately: `max(0, xW1+b1)W2+b2`; d_model = 512, d_ff = 2048 | 3.3 | Inside the models; no action needed |
| **Embeddings** | Learned vectors for tokens (size d_model = 512), scaled by √d_model | 3.4 | **Yes**: embeddings are our main product (one vector per article) |
| **Positional encoding** | Attention itself ignores word order, so sine and cosine waves of different frequencies are added to give each position an identity; learned positions gave nearly identical results (Table 3 row E) | 3.5 | Inside the models |
| **Training and regularisation** | Adam optimiser, learning-rate warm-up of 4,000 steps, dropout 0.1, label smoothing 0.1 | 5.3, 5.4 | Only needed if we fine-tune |
| **Why self-attention** | Table 1: self-attention costs O(n²·d) per layer, O(1) sequential steps and O(1) path length between any two words; a recurrent layer costs O(n·d²), O(n) steps and O(n) path length | 4 | Explains why we must **limit text length** (see section 6) |

**Paper facts that matter for planning**

- The paper trained the base model (about 65M parameters, Table 3) for 100,000 steps in 12 hours on 8 NVIDIA P100 GPUs, with batches of about 25,000 source tokens, on 4.5 million sentence pairs. The big model (213M parameters) took 3.5 days. [Paper §5.1-5.2, Table 3]
- Results: 28.4 BLEU (English to German) and 41.8 BLEU (English to French) for the big model; the base model's training cost was 3.3 × 10¹⁸ FLOPs. [Paper, Table 2]
- The paper tests **translation and parsing, not classification or similarity**. It shows nothing about news. It only shows that the architecture learns useful relationships between words, for example Figure 3, where "making" attends to "more difficult" far away in the sentence. Any claim that Transformers help our news project must be **tested on our data**, not taken from the paper.

**What is not in the paper** [My background knowledge]: models such as BERT and the sentence-embedding models below reuse the paper's *encoder* idea, are trained on huge text collections, and are then shared for free. We would use such a ready-made encoder. Turning a model's output into one vector per text is done by an extra step called pooling (for example, averaging the word vectors), which is not part of the paper.

---

## 2. Existing project assessment

### What is completed [Repo, verified in the documentation work]

| Stage | Result |
|---|---|
| Scraping | 100,028 articles in SQLite; 100,027 in the CSV; 204 listed sources |
| PostgreSQL import | `public.articles`: 100,026 rows (database `task3_articles`, user `task3_user`) |
| Preprocessing | `public.articles_cleaned`: 100,026 rows, original columns plus 11 added columns; 724 encoding repairs; 266 duplicate groups, 779 later copies flagged; 2,584 non-article pages flagged |
| Validation | 93,311 ACCEPT / 6,715 WARNING / 0 QUARANTINE; **95,094 ML-ready** articles; 4,932 excluded |
| EDA | Charts 01 to 07, 10 to 14; domain derived from the URL in SQL (not from the `source` column) |
| Rule-based classification | All 95,094 articles labelled with 7 labels (`market_stocks`, `technology`, `health`, `energy`, `politics`, `other`, `uncertain`); accuracy 68.5% (round 1, hand labels) and 73.0% (round 2, assistant labels, not spot-checked) |
| ML preparation | 71,674 "safe to train on"; 71,319 after keeping one article per title |
| Documentation | Four documents plus `MASTER_PROJECT_DOCUMENTATION.md` |

Your Phase 1 brief lists the work up to "initial validation and exploratory analysis". The repository goes further: it already contains a **rule-based classifier** with your five topics, and a **hand-labelled test set** of 300 articles. This changes the plan (section 5).

### Reusable assets and weaknesses relevant to Transformers

| Asset or fact | Why it matters |
|---|---|
| `articles_cleaned` (read-only source), `data_ml_ready.csv` (95,094 ids) | The text source and the list of articles fit for ML |
| Rule labels for all articles (`articles_classified.csv`) | Cheap, noisy labels (a "weak" training signal) |
| 300 hand labels (200 by you, 100 by an assistant) | **The only real answer key.** The label files are on your computer in `analysis_output/`; **they are not in the repository** |
| Domain-only baseline 67.6% | A text model must clearly beat this, so train/test must be split **by domain** |
| Class sizes: 30,696 `other` vs 724 `energy` among safe-to-train articles (42 to 1) | Needs class weights and a metric that does not hide small classes (macro-F1) |
| 65,322 of 95,094 articles are from 2026 | Time skew; a random split would mix periods |
| `description` and `language` are 100% empty | We cannot use them; text comes from `title` and `body` only |
| Round-2 labels not spot-checked; finance rules (`market_stocks`) untested | Gold labels need strengthening before we can trust a comparison |
| 10,716 `uncertain` articles (including 1,234 company-profile pages) | Not real topics: keep them out of training |

### Database inspection: what I could and could not do

My workspace is a cloud sandbox with **no connection to your PostgreSQL server**, so I could not look at the live database. I used the schema files and the documented results instead:

- `public.articles`: `id, url, source, title, author, published_date, published_time, description, tags, language, body, word_count, method, imported_at` (from `schema.sql`).
- `public.articles_cleaned`: the same 14 columns plus `clean_word_count, body_hash, duplicate_group_size, is_duplicate, encoding_repaired, has_suspicious_encoding, is_non_article, author_missing, is_short, has_html_tags, has_boilerplate` (from `preprocess.py`).

**Not verified:** live row counts, table sizes, and whether anything changed since the documentation. Please run the read-only commands in section 8, item 1, and paste the output.

---

## 3. Practical applications of Attention and Transformers

| Application | Feasible on 8 GB RAM, no paid service? | Useful? | Data available? | Verdict |
|---|---|---|---|---|
| **Contextual embeddings** (one vector per article) | Yes with a small pretrained model | High: everything else builds on it | 95,094 articles | **Do first** |
| **Similarity and related stories** (nearest neighbours of embeddings) | Yes (chunked maths, section 4) | High; also finds near-duplicates | Known duplicate groups give a free test | **Do second** |
| **News categorisation** (classifier on embeddings) | Yes (a small classifier on 384 numbers per article) | High | Rule labels (noisy) plus 300 hand labels | **Do third**, evaluated on hand labels |
| **Topic understanding** (clusters of embeddings) | Yes | Medium: finds topics the rules miss; helps `uncertain` and `other` | Same embeddings | Optional after the above |
| **Semantic understanding** | This is what embeddings give | n/a | n/a | Covered by the first item |
| **Zero-shot categorisation** (no training labels) | Needs bigger models | Medium: useful as a comparison | None needed | Optional, only if memory allows (check model size first) |
| **Fine-tuning a small Transformer** | Slow on CPU; possible on a small sample | Maybe, only if embeddings plus a simple classifier are not good enough | Same labels | **Decide after Phase 5 results** |
| **Summarisation of long articles** | Requires an encoder-decoder (the full paper design); models are larger and slower on CPU | Low for your goals; **cannot be scored** without reference summaries | None | **Defer**; not recommended now |
| **Training a Transformer from scratch** | No | n/a | Far too little data | **Do not do** |

---

## 4. Recommended technical approach

**Use a free pretrained model, frozen (no training of the Transformer itself), and put a small classifier on top.**

Why pretrained rather than from scratch, using the paper's own numbers:

- The paper's base model needed **12 hours on 8 P100 GPUs**; we have a laptop-class machine with 8 GB RAM and no confirmed GPU.
- It trained on **4.5 million sentence pairs**; we have 95,094 articles and only 300 hand labels.
- A model trained from scratch on our data would learn little language and would mostly relearn our noisy rule labels.

**Candidate models** (free, open source, English)

| Model | Facts | Source | Fit |
|---|---|---|---|
| `sentence-transformers/all-MiniLM-L6-v2` | About 22.7M parameters, 6 layers, **384-dimensional** output, **texts longer than 256 word pieces are cut off**, about 80 to 90 MB, Apache-2.0 | [Web] third-party copies of the model card | **First choice**: small, fast, easy |
| `BAAI/bge-small-en-v1.5` | **384** dimensions, **512** maximum tokens (the page did not state size or license) | [Web] | Second choice: longer text; confirm size and license on download |
| Larger models (for example `all-mpnet-base-v2`) | Not checked | none | Only if the small models are not good enough and RAM allows |

I will confirm each model's size, license and length limit on the official model page when we download it (Phase 3). The official pages were not reachable from my workspace.

**Pipeline (everything runs locally)**

1. **Input text** = title + the first part of the body (the existing rules also use the title and the first 1,500 characters). The model reads at most 256 word pieces, which is **roughly 1,000 characters** [rule of thumb of about 4 characters per token; to be measured in Phase 2]. So the model sees the title and the opening, which is where news puts its main point.
2. **Embeddings**: encode each article once, in batches, and save them to a file with the article id: 95,094 × 384 numbers is about **146 MB** in 32-bit floats (73 MB in 16-bit). Computed once, cached, resumable, so the 95,094 articles are never processed twice.
3. **Similarity**: with normalised vectors, cosine similarity is a dot product. The full 95,094 × 95,094 matrix would be about **36 GB**, so it is **never built**; instead compute the top-k neighbours in chunks of about 500 rows (about 190 MB per chunk).
4. **Classification**: logistic regression (or a similar simple model) on the embeddings. Train on rule labels where the rules are confident, **test on hand labels**.
5. **Evaluation**: see below.

**Evaluation plan (no invented numbers; every result is recorded as it is measured)**

| Task | Metrics | Test data |
|---|---|---|
| Classification | Accuracy, **macro-F1**, per-class precision, recall and F1, confusion matrix, Wilson 95% ranges (already in the project) | Hand labels (300 now; more is better) |
| Split rules | Split train/test **by domain** (and check by time) so the model cannot just recognise a website; compare with the domain-only baseline 67.6% and the rule classifier (68.5% and 73.0%) | n/a |
| Near-duplicate retrieval | For the 266 known duplicate groups, does an article's nearest neighbour come from the same group (recall at k)? This is a measurable test **without any new labelling** | Existing flags |
| Related stories | A small sample (for example 50 article pairs) checked by you | Manual |
| Clusters (optional) | Compare to rule labels; read samples | Manual |

**Categories.** You planned five (Market/Stock, Technology, Health, Energy, Politics). I recommend **six classes: the five plus `other`**, because 38% of articles are about none of the five (sports, entertainment and so on); forcing them into five classes would be wrong. `uncertain` and non-article pages stay out of training. **Please confirm.**

**Domains.** As you asked, domain names come from the article URL, not from the `source` column (the project already does this in SQL).

---

## 5. Proposed project architecture

Created only after approval (Phase 2), at the repository root, separate from the other stages:

```text
news_intelligence/
  README.md              what it is, how to run, results so far
  requirements.txt       torch (CPU), sentence-transformers, scikit-learn, numpy, pandas, psycopg2-binary, python-dotenv, matplotlib, pytest
  .env.example           placeholders only (real .env is git-ignored)
  .gitignore             .env, artifacts/
  config.py              paths, model name, text length, batch size, seeds
  data_access.py         READ-ONLY connection (same pattern as the validation stage); loads ids + title + lead text; domain from URL
  text_prep.py           builds the model input; length statistics
  embeddings.py          model loading, batch encoding, resumable cache (artifacts/)
  classify.py            trains and applies the classifier on embeddings
  similarity.py          chunked nearest-neighbour search, related stories, near-duplicate test
  evaluate.py            metrics, confusion matrix, Wilson ranges, gold-label loading
  explore.py             text-length and embedding sanity checks (EDA for this project)
  reports/experiments.md every experiment: date, settings, real result
  tests/                 small tests that need no database and no model download
  artifacts/             git-ignored: embeddings, neighbour lists, trained classifier
```

| Your requested area | File |
|---|---|
| Data access | `data_access.py` |
| Exploratory analysis | `explore.py` |
| Text processing | `text_prep.py` |
| Transformer models, embeddings | `embeddings.py` |
| News classification | `classify.py` |
| Similarity analysis | `similarity.py` |
| Evaluation | `evaluate.py` |
| Reports and documentation | `README.md`, `reports/experiments.md` |

About 10 code files plus tests; no notebooks. Safety rules built in: read-only database connection, passwords only from environment variables, no write to any existing table, outputs go to files in `news_intelligence/artifacts/`. If you later want embeddings stored in PostgreSQL, that needs a **new** table, created only with your approval.

---

## 6. Expected challenges and limitations

| Challenge | Why | Plan |
|---|---|---|
| 8 GB RAM, GPU unknown | Neural models use memory; CPU is slower | Small model, batches of about 32, 256-token limit; **benchmark on 1,000 articles first** and measure time and memory. I have **no speed figure for your machine**; I will not guess |
| Quadratic cost of attention | Table 1: O(n²·d). Doubling length from 256 to 512 gives 4 times as many attention entries (65,536 to 262,144 per head) | Limit text to title + opening |
| Long articles are cut | The model sees only the beginning (roughly 1,000 characters); details later in an article are lost | Acceptable for topic; test whether it hurts |
| Label quality | Rule labels are noisy; 73.0% is an assistant-labelled estimate; finance rules untested | Evaluate only on hand labels; extend the hand-labelled set (for example 300 more articles, with disclosure of who labelled) |
| Only 300 gold labels | Small groups give wide ranges (for example energy and market_stocks have few examples) | Report Wilson ranges; do not claim differences that the ranges do not support |
| Circular evaluation | A classifier trained on rule labels may copy the rules | Report agreement with rules separately from accuracy on hand labels |
| Domain shortcut and time skew | Domain alone gives 67.6%; 69% of articles are from 2026 | Split by domain and by time |
| Class imbalance (42 to 1) | Energy is rare | Class weights; report macro-F1 |
| Heavy install | PyTorch is a large download [size not verified]; needs the internet once, then runs offline | Check disk space; use the CPU build unless a GPU is confirmed |
| Model downloads | The model files come from the internet once | Confirm license and size at download |
| English only | The classifier already marks about 1,746 articles as not English | Exclude them or test separately |
| Summaries cannot be scored | No reference summaries | Defer |

---

## 7. Detailed implementation roadmap

Each phase ends with a report and **stops for your approval**.

| Phase | What I will do | Files created or changed | Test | Output you receive |
|---|---|---|---|---|
| **2. Setup and data access** | Create `news_intelligence/` skeleton; read-only data loader; confirm DB structure; check hardware (RAM, CPU, GPU); measure text lengths in tokens on a sample; fix the maximum length | `config.py`, `data_access.py`, `text_prep.py`, `explore.py`, `requirements.txt`, `.env.example`, `.gitignore`, `README.md`, tests | Unit tests; a read-only query that returns counts matching the documented 100,026 / 95,094 | Real hardware facts, text-length statistics, any mismatch with the documentation |
| **3. Embeddings** | Pilot on 1,000 articles (speed, memory, sanity checks such as "two articles about the same event are closer than unrelated ones"); then the full run in resumable chunks | `embeddings.py`, `reports/experiments.md` | Tests of the cache and of resuming; pilot results | `artifacts/` embeddings and a measured run time |
| **4. Similarity** | Chunked top-k neighbours; near-duplicate recall on the 266 duplicate groups; related-stories demo; sample for your manual check | `similarity.py` | Recall at k measured; 50-pair review | Real recall numbers and examples |
| **5. Classification and evaluation** | Train on confident rule labels, split by domain; test on hand labels; compare with the rules and the domain baseline; error analysis | `classify.py`, `evaluate.py` | Metrics with Wilson ranges; confusion matrix | A clear verdict: is the Transformer approach better than the rules, with real numbers |
| **6. Decide next steps** | Only if useful: clustering to help `uncertain` and `other`; more gold labels; a fine-tuning trial on a small sample; zero-shot comparison; summarisation feasibility | depends on results | experiment log | Recommendation, not a promise |
| **7. Documentation** | Update the README and the master documentation with real results | docs only | consistency review | Final report |

---

## 8. What I need from you before Phase 2

1. **Read-only database check.** Run in PowerShell (it asks for your password; it only reads), and paste the output:

```powershell
psql -U task3_user -h localhost -d task3_articles -c "SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_schema='public' AND table_name IN ('articles','articles_cleaned') ORDER BY table_name, ordinal_position;"
psql -U task3_user -h localhost -d task3_articles -c "SELECT (SELECT COUNT(*) FROM public.articles) AS articles, (SELECT COUNT(*) FROM public.articles_cleaned) AS cleaned;"
```

2. **Hardware check** (PowerShell), paste the output:

```powershell
Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores
Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM
Get-PSDrive C | Select-Object Used, Free
```

3. **Decisions**
   - Do you approve the **six classes** (five topics plus `other`)?
   - Is the first model, **`all-MiniLM-L6-v2`** (about 22.7M parameters), acceptable? Installing PyTorch and the model needs a one-time internet download.
   - Do you accept that the project stays **file-based** (embeddings in `news_intelligence/artifacts/`) and does **not** create any new database table unless you approve it later?
   - Are your hand-label files (`my_labels.csv`, `my_labels_round2.csv` and their review sample files) still in `data_analysis_task\analysis_output\`? I will need their path in Phase 2 (copy only; I will not edit them).
   - Are you willing to hand-label or approve a further sample of articles later (Phase 5), so the test set is bigger than 300? I will not substitute assistant labels without telling you.

**Waiting for:** your review and an explicit "approve Phase 2".
