"""Phase 4: find similar articles with the saved vectors. Read-only; nothing is changed.

    python similarity.py --verify                 check the saved vectors are complete and sane
    python similarity.py --build                  nearest 10 neighbours of every article
    python similarity.py --dup-test               do known duplicate copies find their original?
    python similarity.py --dup-diagnose           why do some known duplicates look dissimilar?
    python similarity.py --peek 38990             first 300 characters of one article's body
    python similarity.py --show 12345 -k 5        titles of the articles most similar to one article
"""
import argparse
import json
import sys

import numpy as np

import config
import data_access
import embeddings


# ---------------------------------------------------------------- vectors
def default_embeddings_dir():
    return embeddings.out_dir_for(f"{config.MODEL_NAME}_len{config.MAX_SEQ_TOKENS}", "full")


def verify_vectors(ids, mat, expected_ids):
    """Facts about the saved vectors. 'ok' is True only if every check passes."""
    ids = np.asarray(ids)
    expected = np.asarray(sorted(expected_ids))
    norms = np.linalg.norm(mat, axis=1) if len(mat) else np.array([])
    rep = {"rows": int(len(ids)), "dim": int(mat.shape[1]) if mat.ndim == 2 else None,
           "dtype": str(mat.dtype), "unique_ids": int(len(set(ids.tolist()))),
           "expected_ids": int(len(expected)),
           "missing_ids": int(len(set(expected.tolist()) - set(ids.tolist()))),
           "unexpected_ids": int(len(set(ids.tolist()) - set(expected.tolist()))),
           "nan_or_inf_rows": int((~np.isfinite(mat).all(axis=1)).sum()) if len(mat) else 0,
           "norm_min": round(float(norms.min()), 5) if len(norms) else None,
           "norm_max": round(float(norms.max()), 5) if len(norms) else None,
           "all_zero_rows": int((norms < 1e-6).sum())}
    rep["ok"] = (rep["rows"] == rep["unique_ids"] == rep["expected_ids"]
                 and rep["missing_ids"] == 0 and rep["unexpected_ids"] == 0
                 and rep["nan_or_inf_rows"] == 0 and rep["all_zero_rows"] == 0
                 and 0.999 <= (rep["norm_min"] or 0) and (rep["norm_max"] or 0) <= 1.001)
    return rep


# ---------------------------------------------------------------- search
def top_k(queries, index, k, chunk=500, query_index_offset=None):
    """Cosine top-k of every query row against `index` (rows must be unit length).

    Works in chunks so the full similarity matrix (about 36 GB for all articles) is never built.
    If query_index_offset is given, query row i IS index row offset+i and is excluded.
    Returns (neighbour_rows, similarities), each (n_queries, k), best first.
    """
    n = len(index)
    k = min(k, n - (1 if query_index_offset is not None else 0))
    out_i = np.empty((len(queries), k), dtype=np.int32)
    out_s = np.empty((len(queries), k), dtype=np.float32)
    for start in range(0, len(queries), chunk):
        q = queries[start:start + chunk]
        sims = q @ index.T
        if query_index_offset is not None:
            rows = np.arange(len(q))
            sims[rows, query_index_offset + start + rows] = -np.inf
        part = np.argpartition(-sims, k - 1, axis=1)[:, :k]
        part_s = np.take_along_axis(sims, part, axis=1)
        order = np.argsort(-part_s, axis=1)
        out_i[start:start + len(q)] = np.take_along_axis(part, order, axis=1)
        out_s[start:start + len(q)] = np.take_along_axis(part_s, order, axis=1)
    return out_i, out_s


# ---------------------------------------------------------------- duplicate test
def duplicate_test(groups, ids, mat, query_vectors, k=10):
    """Does each flagged later copy find an earlier copy of itself among its neighbours?

    groups: {hash: [(id, is_duplicate), ...]}   ids/mat: the index
    query_vectors: {article_id: vector} for the later copies to test
    A query counts only if at least one other member of its group is in the index.
    """
    row_of = {int(a): i for i, a in enumerate(ids)}
    tests = []
    for members in groups.values():
        for art_id, is_dup in members:
            if not is_dup or art_id not in query_vectors:
                continue
            targets = {row_of[m] for m, _ in members if m != art_id and m in row_of}
            if targets:
                tests.append((art_id, targets))
    skipped = sum(1 for m in groups.values() for a, d in m if d and a in query_vectors) - len(tests)
    if not tests:
        return {"queries_tested": 0, "queries_without_target_in_index": skipped}
    Q = np.array([query_vectors[a] for a, _ in tests], dtype=np.float32)
    nbr, sim = top_k(Q, mat, k + 1)
    hit = {1: 0, 5: 0, k: 0}
    best_sims = []
    for (art_id, targets), rows, s in zip(tests, nbr, sim):
        keep = [(r, v) for r, v in zip(rows, s) if int(ids[r]) != art_id][:k]
        rank = next((p for p, (r, _) in enumerate(keep, 1) if int(r) in targets), None)
        for cut in hit:
            if rank is not None and rank <= cut:
                hit[cut] += 1
        best_sims.append(float(max(float(Q[len(best_sims)] @ mat[t]) for t in targets)))
    n = len(tests)
    return {"queries_tested": n, "queries_without_target_in_index": skipped,
            "recall_at_1": round(hit[1] / n, 4), "recall_at_5": round(hit[5] / n, 4),
            f"recall_at_{k}": round(hit[k] / n, 4),
            "similarity_to_closest_original": {
                "min": round(min(best_sims), 4), "p10": round(float(np.percentile(best_sims, 10)), 4),
                "median": round(float(np.median(best_sims)), 4)}}


def _pct(values):
    v = np.asarray(values, dtype=float)
    return {"min": round(float(v.min()), 4), "p10": round(float(np.percentile(v, 10)), 4),
            "p25": round(float(np.percentile(v, 25)), 4), "median": round(float(np.median(v)), 4)}


def _norm_text(t):
    return " ".join((t or "").lower().split())


def diagnose_pairs(pairs, encode_fn, low_cut=0.9, n_examples=8):
    """Why do some known duplicate pairs look dissimilar? `pairs` = [(copy, original), ...] of Articles.

    Encodes each pair three ways (title+lead as in the index, lead only, title only) and shows how
    the similarity changes, plus how often titles, leads and websites differ.
    encode_fn(list_of_texts) must return unit-length vectors.
    """
    from text_prep import build_model_text
    if not pairs:
        return {"pairs": 0}
    texts = {"full": ([], []), "lead": ([], []), "title": ([], [])}
    for c, o in pairs:
        for key, fn in (("full", lambda a: build_model_text(a.title, a.lead)),
                        ("lead", lambda a: build_model_text("", a.lead)),
                        ("title", lambda a: build_model_text(a.title, ""))):
            texts[key][0].append(fn(c))
            texts[key][1].append(fn(o))
    sims = {}
    for key, (cs, os_) in texts.items():
        a, b = encode_fn(cs), encode_fn(os_)
        sims[key] = (a * b).sum(axis=1)
    same_title = np.array([_norm_text(c.title) == _norm_text(o.title) for c, o in pairs])
    same_lead = np.array([_norm_text(c.lead) == _norm_text(o.lead) for c, o in pairs])
    same_domain = np.array([c.domain == o.domain for c, o in pairs])
    low = sims["full"] < low_cut
    rep = {"pairs": len(pairs),
           "share_same_title": round(float(same_title.mean()), 4),
           "share_identical_lead": round(float(same_lead.mean()), 4),
           "share_same_website": round(float(same_domain.mean()), 4),
           "similarity_title_plus_lead": _pct(sims["full"]),
           "similarity_lead_only": _pct(sims["lead"]),
           "similarity_title_only": _pct(sims["title"]),
           f"pairs_below_{low_cut}": int(low.sum())}
    if low.any():
        rep["among_low_pairs"] = {
            "share_same_title": round(float(same_title[low].mean()), 4),
            "share_identical_lead": round(float(same_lead[low].mean()), 4),
            "share_same_website": round(float(same_domain[low].mean()), 4),
            "median_lead_only_similarity": round(float(np.median(sims["lead"][low])), 4)}
    worst = np.argsort(sims["full"])[:n_examples]
    rep["lowest_pairs"] = [{"copy_id": pairs[i][0].id, "original_id": pairs[i][1].id,
                            "copy_title": pairs[i][0].title[:80], "original_title": pairs[i][1].title[:80],
                            "websites": f"{pairs[i][0].domain} / {pairs[i][1].domain}",
                            "identical_lead": bool(same_lead[i]),
                            "sim_full": round(float(sims["full"][i]), 3),
                            "sim_lead_only": round(float(sims["lead"][i]), 3),
                            "sim_title_only": round(float(sims["title"][i]), 3)} for i in worst]
    return rep


def neighbour_summary(sims):
    """How similar is the closest other article, for ordinary articles? (top-1 column)"""
    top1 = sims[:, 0]
    return {"top1_similarity_percentiles": {str(p): round(float(np.percentile(top1, p)), 4)
                                            for p in (1, 5, 25, 50, 75, 95, 99)},
            "share_top1_at_least_0.95": round(float((top1 >= 0.95).mean()), 4),
            "share_top1_at_least_0.90": round(float((top1 >= 0.90).mean()), 4),
            "share_top1_at_least_0.80": round(float((top1 >= 0.80).mean()), 4)}


# ---------------------------------------------------------------- command line
def save_json(name, data):
    config.ARTIFACTS_DIR.mkdir(exist_ok=True)
    path = config.ARTIFACTS_DIR / name
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--verify", action="store_true")
    g.add_argument("--build", action="store_true")
    g.add_argument("--dup-test", action="store_true")
    g.add_argument("--dup-diagnose", action="store_true")
    g.add_argument("--peek", type=int, metavar="ARTICLE_ID",
                   help="print the first 300 characters of one article's body")
    g.add_argument("--show", type=int, metavar="ARTICLE_ID")
    p.add_argument("-k", type=int, default=10)
    p.add_argument("--chunk", type=int, default=500, help="queries per block (memory: chunk x 95,094 x 4 bytes)")
    p.add_argument("--embeddings-dir", default=None)
    args = p.parse_args(argv)
    try:
        if args.peek:
            conn = data_access.get_readonly_connection()
            try:
                row = data_access.fetch_body_peek(conn, args.peek)
            finally:
                conn.close()
            if row is None:
                print(f"article {args.peek} not found")
                return 1
            print(f"title: {row['title']}\nbody starts: {' '.join(row['body_start'].split())}")
            return 0
        out_dir = type(config.ARTIFACTS_DIR)(args.embeddings_dir) if args.embeddings_dir \
            else default_embeddings_dir()
        ids, mat = embeddings.load_embeddings(out_dir)
        if args.verify:
            rep = verify_vectors(ids, mat, data_access.load_ml_ready_ids())
            print(json.dumps(rep, indent=2))
            print(f"(saved to {save_json('phase4_verify.json', rep)})")
            return 0 if rep["ok"] else 2
        if args.build:
            nbr, sim = top_k(mat, mat, args.k, args.chunk, query_index_offset=0)
            config.ARTIFACTS_DIR.mkdir(exist_ok=True)
            np.savez(config.ARTIFACTS_DIR / "neighbors.npz", ids=ids,
                     neighbor_ids=ids[nbr].astype(np.int64), similarities=sim)
            rep = {"articles": int(len(ids)), "k": int(nbr.shape[1]), **neighbour_summary(sim)}
            print(json.dumps(rep, indent=2))
            print(f"(saved neighbors.npz and {save_json('phase4_neighbors_summary.json', rep)})")
            return 0
        conn = data_access.get_readonly_connection()
        try:
            if args.show:
                row = {int(a): i for i, a in enumerate(ids)}.get(args.show)
                if row is None:
                    print(f"article {args.show} is not among the embedded articles")
                    return 1
                nbr, sim = top_k(mat[row:row + 1], mat, args.k, 1, query_index_offset=row)
                wanted = [args.show] + [int(ids[r]) for r in nbr[0]]
                info = {a.id: a for a in data_access.fetch_articles(conn, wanted, lead_chars=1)}
                print(f"{args.show}  [{info[args.show].domain}]  {info[args.show].title[:90]}")
                for r, s in zip(nbr[0], sim[0]):
                    a = info[int(ids[r])]
                    print(f"  {s:.3f}  {a.id}  [{a.domain}]  {a.title[:90]}")
                return 0
            groups = data_access.fetch_duplicate_groups(conn)
            if args.dup_diagnose:
                in_index = set(ids.tolist())
                want = []
                for m in groups.values():
                    originals = [a for a, d in m if not d and a in in_index]
                    if originals:                      # first original of the group, no cherry-picking
                        want += [(a, originals[0]) for a, d in m if d]
                arts = {a.id: a for a in data_access.fetch_articles(
                    conn, sorted({x for pair in want for x in pair}))}
                pairs = [(arts[c], arts[o]) for c, o in want if c in arts and o in arts]
                print(f"{len(pairs)} (copy, original) pairs; encoding 3 ways ...")
                enc = embeddings.load_encoder(config.MODEL_NAME, config.MAX_SEQ_TOKENS)
                rep = diagnose_pairs(pairs, lambda t: embeddings.encode(enc, t, 8))
                print(json.dumps(rep, indent=2))
                print(f"(saved to {save_json('phase4b_duplicate_diagnosis.json', rep)})")
                return 0
            later = sorted({a for m in groups.values() for a, d in m if d})
            if not later:
                print("no flagged duplicate copies found")
                return 1
            print(f"{len(groups)} duplicate groups, {len(later)} flagged later copies; embedding them ...")
            from text_prep import build_model_text
            arts = list(data_access.fetch_articles(conn, later))
        finally:
            conn.close()
        enc = embeddings.load_encoder(config.MODEL_NAME, config.MAX_SEQ_TOKENS)
        vecs = embeddings.encode(enc, [build_model_text(a.title, a.lead) for a in arts], 8)
        rep = duplicate_test(groups, ids, mat, {a.id: v for a, v in zip(arts, vecs)}, args.k)
        rep["later_copies_in_index"] = int(sum(1 for a in later if a in set(ids.tolist())))
        print(json.dumps(rep, indent=2))
        print(f"(saved to {save_json('phase4_duplicate_test.json', rep)})")
        return 0
    except (config.ConfigError, FileNotFoundError, ValueError, ImportError) as exc:
        print("PROBLEM:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
