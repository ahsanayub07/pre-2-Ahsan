import numpy as np

from svm_model import SVM, OneVsRestSVM, Pipeline


def notebook_gradient(X, y, w, b, C):
    """The gradient exactly as written in the company notebook."""
    margin = y * (X @ w + b)
    mask = (margin < 1).astype(float)
    dw = w - C * np.mean((y[:, None] * X) * mask[:, None], axis=0)
    db = -C * np.mean(y * mask)
    return dw, db


def test_gradient_matches_notebook_formula():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(50, 4)); y = np.where(rng.random(50) < 0.5, -1.0, 1.0)
    w = rng.normal(size=4); b = 0.3; C = 2.0
    dw_ref, db_ref = notebook_gradient(X, y, w, b, C)
    mask = (y * (X @ w + b) < 1)
    dw = w - C * (X.T @ (y * mask)) / len(y)
    db = -C * float((y * mask).sum()) / len(y)
    assert np.allclose(dw, dw_ref) and abs(db - db_ref) < 1e-12


def blobs(n, centres, spread, seed):
    rng = np.random.default_rng(seed)
    y = np.array([i % len(centres) for i in range(n)])
    X = np.array([centres[c] + rng.normal(size=len(centres[0])) * spread for c in y])
    return X.astype(np.float32), y


def test_binary_learns_separable_data():
    X, y = blobs(200, [np.array([-2.0, 0]), np.array([2.0, 0])], 0.5, 1)
    m = SVM(learning_rate=0.05, epochs=500, C=1.0, seed=0).fit(X, y)
    assert (m.predict(X) == y).mean() > 0.97


def test_accepts_plus_minus_one_labels():
    X, y = blobs(100, [np.array([-2.0, 0]), np.array([2.0, 0])], 0.4, 2)
    m = SVM(learning_rate=0.05, epochs=300, C=1.0, seed=0).fit(X, np.where(y == 0, -1, 1))
    assert (m.predict(X) == y).mean() > 0.97


def test_one_vs_rest_three_classes():
    cs = [np.array([3.0, 0, 0]), np.array([0, 3.0, 0]), np.array([0, 0, 3.0])]
    X, y = blobs(300, cs, 0.6, 3)
    m = OneVsRestSVM(learning_rate=0.05, epochs=400, C=1.0, seed=0).fit(X, y)
    assert (np.array(m.predict(X)) == y).mean() > 0.95
    assert m.classes_ == [0, 1, 2]


def test_balanced_weights_and_rare_class():
    rng = np.random.default_rng(4)
    X = np.vstack([rng.normal(size=(990, 2)) + [2, 0], rng.normal(size=(10, 2)) + [-2, 0]]).astype(np.float32)
    y = np.array([0] * 990 + [1] * 10)
    w = SVM(balanced=True)._weights(np.where(y == 1, 1.0, -1.0))
    assert abs(w[y == 1][0] - 50.0) < 1e-4 and abs(w[y == 0][0] - 500 / 990) < 1e-4
    plain = SVM(learning_rate=0.05, epochs=400, C=1.0, seed=0).fit(X, y)
    bal = SVM(learning_rate=0.05, epochs=400, C=1.0, seed=0, balanced=True).fit(X, y)
    assert bal.predict(X)[y == 1].mean() >= plain.predict(X)[y == 1].mean()


def test_moons_with_polynomial_features_like_the_notebook():
    from sklearn.datasets import make_moons
    from sklearn.preprocessing import PolynomialFeatures, StandardScaler
    X, y = make_moons(n_samples=300, noise=0.1, random_state=0)
    lin = Pipeline(StandardScaler(), SVM(learning_rate=0.05, epochs=2000, C=1.0, seed=0)).fit(X, y)
    poly = Pipeline(PolynomialFeatures(degree=5, include_bias=False), StandardScaler(),
                         SVM(learning_rate=0.05, epochs=3000, C=1.0, seed=0)).fit(X, y)
    assert (poly.predict(X) == y).mean() > (lin.predict(X) == y).mean()
    assert (poly.predict(X) == y).mean() > 0.85
