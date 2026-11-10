"""Phase 3: turn each article into one vector with a pretrained BERT-style encoder.

The encoder is frozen (no training). Vectors are saved in shards so an interrupted run
resumes where it stopped, and nothing is ever written to the database.

    python embeddings.py --pilot 1000                       speed + memory test, 1,000 articles
    python embeddings.py --pilot 1000 --model bert-base-uncased
    python embeddings.py --full                             all ML-ready articles (resumable)
"""
import argparse
import json
import random
import re
import sys
import time

import numpy as np

import config
import data_access
from text_prep import build_model_text

SHARD_SIZE = 2000                      # articles per saved file


def model_slug(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


def out_dir_for(model_name, kind):
    d = config.ARTIFACTS_DIR / "embeddings" / f"{kind}_{model_slug(model_name)}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_encoder(model_name, max_seq_length=None):
    """Load the pretrained encoder. A plain BERT checkpoint gets mean pooling automatically.

    max_seq_length: word-pieces read per article (default: the model's own setting, at most 512).
    """
    from sentence_transformers import SentenceTransformer     # needs: pip install sentence-transformers
    model = SentenceTransformer(model_name, device="cpu")
    wanted = max_seq_length or model.max_seq_length or config.MAX_SEQ_TOKENS
    model.max_seq_length = min(int(wanted), 512)
    return model


def rss_gb():
    try:
        import psutil
        return round(psutil.Process().memory_info().rss / 1e9, 2)
    except ImportError:
        return None


def encode(encoder, texts, batch_size):
    """Unit-length float32 vectors, one row per text."""
    vecs = encoder.encode(texts, batch_size=batch_size, normalize_embeddings=True,
                          show_progress_bar=False, convert_to_numpy=True)
    return np.asarray(vecs, dtype=np.float32)


def shard_path(out_dir, n):
    return out_dir / f"shard_{n:05d}.npz"


def embed_ids(encoder, ids, fetch, out_dir, batch_size, shard_size=SHARD_SIZE, log=print):
    """Embed `ids` shard by shard. Existing shards are skipped (resume). Returns stats."""
    ids = sorted(ids)
    stats = {"articles_done": 0, "articles_skipped_resume": 0, "seconds_encoding": 0.0,
             "peak_rss_gb": rss_gb(), "empty_text": 0}
    for n, start in enumerate(range(0, len(ids), shard_size)):
        part = ids[start:start + shard_size]
        path = shard_path(out_dir, n)
        if path.exists():
            stats["articles_skipped_resume"] += len(part)
            continue
        arts = list(fetch(part))
        texts = [build_model_text(a.title, a.lead) for a in arts]
        stats["empty_text"] += sum(1 for t in texts if not t)
        t0 = time.perf_counter()
        vecs = encode(encoder, texts, batch_size)
        stats["seconds_encoding"] += time.perf_counter() - t0
        tmp = path.with_suffix(".tmp.npz")                      # write then rename: no half files
        np.savez(tmp, ids=np.array([a.id for a in arts], dtype=np.int64), vectors=vecs)
        tmp.replace(path)
        stats["articles_done"] += len(arts)
        stats["peak_rss_gb"] = max(filter(None, [stats["peak_rss_gb"], rss_gb()]), default=None)
        log(f"shard {n}: {len(arts)} articles, {stats['seconds_encoding']:.0f}s encoding so far")
    stats["seconds_encoding"] = round(stats["seconds_encoding"], 2)
    return stats


def load_embeddings(out_dir):
    """All shards of a run as (ids, matrix), sorted by id."""
    files = sorted(out_dir.glob("shard_*.npz"))
    if not files:
        raise FileNotFoundError(f"no shards in {out_dir}")
    parts = [np.load(f) for f in files]
    ids = np.concatenate([p["ids"] for p in parts])
    mat = np.concatenate([p["vectors"] for p in parts])
    order = np.argsort(ids)
    return ids[order], mat[order]


def write_meta(out_dir, model_name, kind, n_articles, stats, batch_size, extra=None):
    meta = {"model": model_name, "kind": kind, "articles_requested": n_articles,
            "batch_size": batch_size, "lead_chars": config.LEAD_CHARS,
            "text_format": "title + '. ' + first lead_chars of body",
            "normalized": True, "seed": config.SEED, **stats, **(extra or {})}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def pilot_summary(stats, n_pilot, n_full):
    """Measured speed, plus a clearly labelled straight-line projection for the full run."""
    secs = stats["seconds_encoding"]
    if not stats["articles_done"] or secs <= 0:
        return {"note": "no new articles encoded (resumed from saved shards)"}
    rate = stats["articles_done"] / secs
    return {"measured_articles_per_second": round(rate, 2),
            "projected_full_run_hours_PROJECTION_NOT_MEASURED": round(n_full / rate / 3600, 2),
            "projection_basis": f"{stats['articles_done']} articles, straight-line"}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--pilot", type=int, metavar="N")
    g.add_argument("--full", action="store_true")
    p.add_argument("--model", default=config.MODEL_NAME)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--max-seq-length", type=int, default=None,
                   help="word-pieces read per article (e.g. 256 or 512); default = model's own")
    args = p.parse_args(argv)
    try:
        all_ids = data_access.load_ml_ready_ids()
        if args.pilot:
            ids = sorted(random.Random(config.SEED).sample(all_ids, min(args.pilot, len(all_ids))))
            kind = f"pilot{len(ids)}"
        else:
            ids, kind = all_ids, "full"
        conn = data_access.get_readonly_connection()
        encoder = None
        print(f"loading {args.model} ...")
        encoder = load_encoder(args.model, args.max_seq_length)
        out_dir = out_dir_for(args.model + f"_len{encoder.max_seq_length}", kind)
        try:
            stats = embed_ids(encoder, ids, lambda part: data_access.fetch_articles(conn, part),
                              out_dir, args.batch_size)
        finally:
            conn.close()
    except (config.ConfigError, FileNotFoundError, ValueError, ImportError) as exc:
        print("PROBLEM:", exc)
        return 1
    extra = {"max_seq_length": getattr(encoder, "max_seq_length", None),
             **pilot_summary(stats, len(ids), len(all_ids))}
    print(json.dumps(write_meta(out_dir, args.model, kind, len(ids), stats, args.batch_size, extra),
                     indent=2))
    print(f"(saved in {out_dir})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
    