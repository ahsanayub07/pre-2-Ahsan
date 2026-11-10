import numpy as np
import pytest

import embeddings
from data_access import Article


class FakeEncoder:
    max_seq_length = 256

    def __init__(self):
        self.calls = 0

    def encode(self, texts, batch_size, normalize_embeddings, show_progress_bar, convert_to_numpy):
        self.calls += 1
        rng = [np.random.default_rng(abs(hash(t)) % (2 ** 32)).normal(size=8) for t in texts]
        m = np.array(rng, dtype=np.float64)
        return m / np.linalg.norm(m, axis=1, keepdims=True)


def fetch(part):
    for i in part:
        yield Article(i, f"https://s.com/{i}", "s.com", f"Title {i}", f"lead text {i}")


def test_slug():
    assert embeddings.model_slug("sentence-transformers/all-MiniLM-L6-v2") == \
        "sentence-transformers_all-MiniLM-L6-v2"


def test_embed_and_load(tmp_path):
    enc = FakeEncoder()
    st = embeddings.embed_ids(enc, [5, 3, 1, 2, 4], fetch, tmp_path, 2, shard_size=2, log=lambda s: None)
    assert st["articles_done"] == 5 and enc.calls == 3
    ids, mat = embeddings.load_embeddings(tmp_path)
    assert list(ids) == [1, 2, 3, 4, 5]
    assert mat.dtype == np.float32 and mat.shape == (5, 8)
    assert np.allclose(np.linalg.norm(mat, axis=1), 1, atol=1e-5)


def test_resume_skips_finished_shards(tmp_path):
    enc = FakeEncoder()
    embeddings.embed_ids(enc, list(range(1, 7)), fetch, tmp_path, 2, shard_size=2, log=lambda s: None)
    enc2 = FakeEncoder()
    st = embeddings.embed_ids(enc2, list(range(1, 7)), fetch, tmp_path, 2, shard_size=2, log=lambda s: None)
    assert enc2.calls == 0 and st["articles_skipped_resume"] == 6 and st["articles_done"] == 0


def test_resume_after_partial(tmp_path):
    enc = FakeEncoder()
    embeddings.embed_ids(enc, [1, 2, 3, 4], fetch, tmp_path, 2, shard_size=2, log=lambda s: None)
    (tmp_path / "shard_00001.npz").unlink()                 # pretend the run stopped here
    enc2 = FakeEncoder()
    st = embeddings.embed_ids(enc2, [1, 2, 3, 4], fetch, tmp_path, 2, shard_size=2, log=lambda s: None)
    assert enc2.calls == 1 and st["articles_done"] == 2
    assert list(embeddings.load_embeddings(tmp_path)[0]) == [1, 2, 3, 4]


def test_load_empty_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        embeddings.load_embeddings(tmp_path)


def test_pilot_summary_is_labelled_projection():
    s = embeddings.pilot_summary({"articles_done": 100, "seconds_encoding": 50.0}, 100, 7200)
    assert s["measured_articles_per_second"] == 2.0
    assert s["projected_full_run_hours_PROJECTION_NOT_MEASURED"] == 1.0
    assert "note" in embeddings.pilot_summary({"articles_done": 0, "seconds_encoding": 0}, 1, 1)
