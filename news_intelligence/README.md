# news_intelligence

Applies Transformer ideas (attention, pretrained sentence encoders) to the project's news
articles, using free local models. **Phase 2: setup and data access. Phase 3: BERT-style embeddings (`embeddings.py`).**

Rules of this folder: `public.articles_cleaned` is only **read** (read-only connection);
nothing is written to the database; the password lives only in a local `.env`; every
experiment result is recorded in `reports/experiments.md` from a real run.

## Files
| File | Purpose |
|---|---|
| `config.py` | Settings, class list, safe loading of database settings |
| `data_access.py` | Read-only connection, ML-ready id list, article fetching in batches |
| `text_prep.py` | Website name from URL, model text (title + opening of body), length statistics |
| `explore.py` | Checks: `--env` (hardware), `--counts` (database), `--lengths N` (text length) |
| `tests/` | 21 tests that need no database and no download; 4 optional database tests |
| `reports/experiments.md` | Log of real results |

## Set up (PowerShell, from the repository root)
```powershell
.\.venv\Scripts\Activate.ps1
cd news_intelligence
pip install -r requirements.txt
Copy-Item .env.example .env      # run once; then open .env and put your real password
```

## Run the tests
```powershell
python -m pytest -q
```

## Run the three checks and send the printed output back
```powershell
python explore.py --env
python explore.py --counts
python explore.py --lengths 2000
```
Results are also saved as small JSON files in `artifacts/` (ignored by Git).
`--lengths` measures word-pieces only if `transformers` is installed and the tokenizer can be
downloaded; otherwise it says "not measured" and still reports character lengths.

## Phase 3: embeddings (run after the Phase 2 checks)
```powershell
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python embeddings.py --pilot 1000                          # MiniLM-L6, 1,000 articles
python embeddings.py --pilot 1000 --model bert-base-uncased --max-seq-length 512
```
The first run downloads the model (needs internet). Output goes to `artifacts/embeddings/`
with a `meta.json` holding the measured speed and memory. Run `--full` only after the pilot
looks fine; it saves in shards, so if it stops, run the same command again to resume.

## Phase 3b: which encoder setup is best? (hand-labelled articles only)
```powershell
pip install -r requirements.txt
python compare_models.py
```
Embeds the ~293 usable hand labels with three setups, trains a simple classifier, and scores it
on websites it did not train on. Results: `artifacts/compare_models.json`.
