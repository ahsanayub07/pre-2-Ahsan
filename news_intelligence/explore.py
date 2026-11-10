"""Phase 2 checks. Read-only: nothing is written except small JSON files in artifacts/.

    python explore.py --env              hardware, Python packages, GPU
    python explore.py --counts           database counts against the documented figures
    python explore.py --lengths 2000     how long the text a model would read really is
"""
import argparse
import json
import platform
import random
import shutil
import subprocess
import sys
from importlib import metadata

import config
import data_access
from text_prep import build_model_text, length_summary


def save_json(name, data):
    config.ARTIFACTS_DIR.mkdir(exist_ok=True)
    path = config.ARTIFACTS_DIR / name
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def package_version(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def gpu_info():
    """NVIDIA GPU name and memory from nvidia-smi, or None (no NVIDIA GPU or no driver)."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=15)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def environment_report():
    rep = {"python": sys.version.split()[0], "os": platform.platform(),
           "cpu_threads": __import__("os").cpu_count(),
           "disk_free_gb_repo": round(shutil.disk_usage(config.REPO_ROOT).free / 1e9, 1),
           "gpu_nvidia_smi": gpu_info(),
           "packages": {p: package_version(p) for p in
                        ("torch", "sentence-transformers", "transformers", "scikit-learn",
                         "numpy", "pandas", "psycopg2-binary", "psutil")}}
    psutil = package_version("psutil") and __import__("psutil")
    if psutil:
        mem = psutil.virtual_memory()
        rep["ram_total_gb"] = round(mem.total / 1e9, 1)
        rep["ram_available_gb"] = round(mem.available / 1e9, 1)
    else:
        rep["ram_total_gb"] = rep["ram_available_gb"] = "psutil not installed"
    if rep["packages"]["torch"]:
        import torch
        rep["torch_cuda_available"] = bool(torch.cuda.is_available())
    return rep


def counts_report():
    ids = data_access.load_ml_ready_ids()
    conn = data_access.get_readonly_connection()
    try:
        got = data_access.table_counts(conn, ids)
    finally:
        conn.close()
    doc = config.DOCUMENTED_COUNTS
    checks = {"articles": got["articles"] == doc["articles"],
              "articles_cleaned": got["articles_cleaned"] == doc["articles_cleaned"],
              "ml_ready_ids": got["ml_ready_ids"] == doc["ml_ready"],
              "all_ml_ready_ids_in_cleaned": got["ml_ready_found_in_cleaned"] == got["ml_ready_ids"]}
    return {"live": got, "documented": doc, "match": checks}


def token_lengths(texts):
    """Word-piece count per text with the model's own tokenizer, or None if unavailable."""
    try:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(config.MODEL_NAME)
    except Exception as exc:                      # no package, no internet, wrong name ...
        return None, f"{type(exc).__name__}: {str(exc)[:160]}"
    return [len(ids) for ids in tok(texts, truncation=False)["input_ids"]], None


def lengths_report(n):
    ids = data_access.load_ml_ready_ids()
    sample = sorted(random.Random(config.SEED).sample(ids, min(n, len(ids))))
    conn = data_access.get_readonly_connection()
    try:
        arts = list(data_access.fetch_articles(conn, sample))
    finally:
        conn.close()
    texts = [build_model_text(a.title, a.lead) for a in arts]
    rep = {"sample_requested": n, "articles_fetched": len(arts), "seed": config.SEED,
           "lead_chars": config.LEAD_CHARS,
           "distinct_domains": len({a.domain for a in arts}),
           "empty_title": sum(1 for a in arts if not a.title.strip()),
           "empty_lead": sum(1 for a in arts if not a.lead.strip()),
           "model_text_chars": length_summary([len(t) for t in texts])}
    tokens, err = token_lengths(texts)
    if tokens is None:
        rep["tokens"] = f"not measured ({err})"
    else:
        rep["tokens"] = length_summary(tokens)
        rep["share_over_max_seq"] = round(sum(t > config.MAX_SEQ_TOKENS for t in tokens) / len(tokens), 4)
        rep["max_seq_tokens"] = config.MAX_SEQ_TOKENS
        rep["model"] = config.MODEL_NAME
    return rep


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--env", action="store_true")
    p.add_argument("--counts", action="store_true")
    p.add_argument("--lengths", type=int, metavar="N")
    args = p.parse_args(argv)
    if not (args.env or args.counts or args.lengths):
        p.print_help()
        return 0
    try:
        for flag, name, fn in ((args.env, "phase2_environment.json", environment_report),
                               (args.counts, "phase2_counts.json", counts_report),
                               (args.lengths, "phase2_lengths.json",
                                lambda: lengths_report(args.lengths))):
            if flag:
                result = fn()
                print(json.dumps(result, indent=2, ensure_ascii=False))
                print(f"(saved to {save_json(name, result)})\n")
    except (config.ConfigError, FileNotFoundError, ValueError) as exc:
        print("PROBLEM:", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
