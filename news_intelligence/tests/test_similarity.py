import numpy as np

import data_access
import similarity


def unit(rows):
    m = np.asarray(rows, dtype=np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def test_top_k_matches_brute_force_with_chunks():
    rng = np.random.default_rng(1)
    X = unit(rng.normal(size=(40, 6)))
    nbr, sim = similarity.top_k(X, X, 5, chunk=7, query_index_offset=0)
    full = X @ X.T
    np.fill_diagonal(full, -np.inf)
    expect = np.argsort(-full, axis=1)[:, :5]
    assert (nbr == expect).all()
    assert (np.diff(sim, axis=1) <= 1e-6).all()          # best first


def test_top_k_excludes_self_and_handles_small_index():
    X = unit([[1, 0], [0, 1], [1, 1]])
    nbr, _ = similarity.top_k(X, X, 10, query_index_offset=0)
    assert nbr.shape == (3, 2)
    assert all(i not in row for i, row in enumerate(nbr))


def test_verify_ok_and_problems():
    X = unit(np.random.default_rng(0).normal(size=(5, 4)))
    ids = np.array([1, 2, 3, 4, 5])
    assert similarity.verify_vectors(ids, X, [1, 2, 3, 4, 5])["ok"]
    assert not similarity.verify_vectors(ids, X, [1, 2, 3, 4, 6])["ok"]            # id mismatch
    assert not similarity.verify_vectors(np.array([1, 1, 3, 4, 5]), X, [1, 3, 4, 5, 1])["ok"]
    bad = X.copy(); bad[2, 0] = np.nan
    assert similarity.verify_vectors(ids, bad, ids)["nan_or_inf_rows"] == 1
    assert not similarity.verify_vectors(ids, X * 2, ids)["ok"]                    # not unit length
    z = X.copy(); z[0] = 0
    assert similarity.verify_vectors(ids, z, ids)["all_zero_rows"] == 1


def test_duplicate_test_recall():
    rng = np.random.default_rng(3)
    mat = unit(rng.normal(size=(30, 8)))
    ids = np.arange(100, 130)
    groups = {"h1": [(100, False), (900, True)], "h2": [(105, False), (901, True)],
              "h3": [(777, False), (902, True)]}                  # h3 original not in the index
    q = {900: mat[0] + 0.001, 901: unit([rng.normal(size=8)])[0], 902: mat[3]}
    rep = similarity.duplicate_test(groups, ids, mat, q, k=5)
    assert rep["queries_tested"] == 2 and rep["queries_without_target_in_index"] == 1
    assert 0.0 <= rep["recall_at_1"] <= 1.0 and rep["recall_at_5"] >= rep["recall_at_1"]
    q[901] = mat[5]                                              # exact copy of its original
    assert similarity.duplicate_test(groups, ids, mat, q, k=5)["recall_at_1"] == 1.0


def test_duplicate_query_that_is_in_the_index_ignores_itself():
    mat = unit([[1, 0, 0], [0.99, 0.1, 0], [0, 1, 0], [0, 0, 1]])
    ids = np.array([1, 2, 3, 4])
    groups = {"h": [(1, False), (2, True)]}
    rep = similarity.duplicate_test(groups, ids, mat, {2: mat[1]}, k=2)
    assert rep["recall_at_1"] == 1.0                              # id 2 must not "find" itself


def test_neighbour_summary():
    s = similarity.neighbour_summary(np.array([[0.99], [0.5], [0.85], [0.2]], dtype=np.float32))
    assert s["share_top1_at_least_0.95"] == 0.25 and s["share_top1_at_least_0.80"] == 0.5


class Cur:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, params=None): self.sql = sql
    def fetchall(self): return [("h1", 1, False), ("h1", 2, True), ("h2", 3, False), ("h2", 4, True)]


class Conn:
    def cursor(self): return Cur()


def test_fetch_duplicate_groups():
    g = data_access.fetch_duplicate_groups(Conn())
    assert g == {"h1": [(1, False), (2, True)], "h2": [(3, False), (4, True)]}


def _fake_encode(texts):
    out = np.zeros((len(texts), 26), dtype=np.float32)
    for i, t in enumerate(texts):
        for ch in t.lower():
            if "a" <= ch <= "z":
                out[i, ord(ch) - 97] += 1
    out[out.sum(axis=1) == 0, 0] = 1
    return out / np.linalg.norm(out, axis=1, keepdims=True)


def test_diagnose_pairs_title_difference_explains_low_similarity():
    A = data_access.Article
    same = (A(1, "u", "a.com", "Same headline here", "lead body text about cats"),
            A(2, "u", "a.com", "Same headline here", "lead body text about cats"))
    retitled = (A(3, "u", "b.com", "zzz qqq xxx www", "lead body text about cats"),
                A(4, "u", "c.com", "Totally other headline", "lead body text about cats"))
    rep = similarity.diagnose_pairs([same, retitled], _fake_encode, low_cut=0.999)
    assert rep["pairs"] == 2 and rep["share_identical_lead"] == 1.0
    assert rep["share_same_title"] == 0.5 and rep["share_same_website"] == 0.5
    assert rep["similarity_lead_only"]["min"] > 0.999                  # identical lead -> identical vector
    assert rep["similarity_title_only"]["min"] < 0.9
    assert rep["lowest_pairs"][0]["copy_id"] == 3                      # the retitled pair is the lowest
    assert similarity.diagnose_pairs([], _fake_encode) == {"pairs": 0}


class PeekCur(Cur):
    def __init__(self, row): self.row = row
    def fetchone(self): return self.row


class PeekConn:
    def __init__(self, row): self.row = row
    def cursor(self): return PeekCur(self.row)


def test_fetch_body_peek():
    assert data_access.fetch_body_peek(PeekConn(("T", "abc")), 1) == {"title": "T", "body_start": "abc"}
    assert data_access.fetch_body_peek(PeekConn((None, None)), 1) == {"title": "", "body_start": ""}
    assert data_access.fetch_body_peek(PeekConn(None), 1) is None
