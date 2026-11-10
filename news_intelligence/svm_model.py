"""Linear SVM trained by gradient descent on the hinge loss, ported from the company's SVM notebook.

Same objective as the notebook:      C * mean(max(0, 1 - y (w.x + b))) + 0.5 * ||w||^2
Same update:                         subgradient descent with learning rate lr / (1 + epoch / 1000)
Differences, on purpose:
  * the gradient is computed as  X.T @ (y * mask) / n  instead of building the (n x features) matrix
    (y[:, None] * X) * mask, which is mathematically identical but needs far less memory;
  * optional per-class weights ('balanced'), because the news classes are very unequal in size;
  * a one-vs-rest wrapper for more than two classes (the notebook is binary only).
"""
import numpy as np


class SVM:
    def __init__(self, learning_rate=0.1, epochs=3000, C=10.0, balanced=False, seed=None, verbose=False):
        self.lr, self.epochs, self.C = learning_rate, epochs, C
        self.balanced, self.seed, self.verbose = balanced, seed, verbose
        self.w = None
        self.b = 0.0
        self.final_loss = None

    def _weights(self, y):
        n = len(y)
        if not self.balanced:
            return np.ones(n, dtype=np.float32)
        pos = max(int((y > 0).sum()), 1)
        neg = max(n - pos, 1)
        return np.where(y > 0, n / (2 * pos), n / (2 * neg)).astype(np.float32)

    def _loss(self, margin, sw):
        return float(self.C * np.mean(sw * np.maximum(0, 1 - margin)) + 0.5 * float(self.w @ self.w))

    def fit(self, X, y):
        X = np.asarray(X)
        if X.dtype not in (np.float32, np.float64):
            X = X.astype(np.float32)
        y = np.where(np.asarray(y) <= 0, -1, 1).astype(X.dtype)      # labels 0/1 or -1/+1
        n, d = X.shape
        rng = np.random.default_rng(self.seed)
        self.w = (rng.normal(size=d) * 0.1).astype(X.dtype)
        self.b = 0.0
        sw = self._weights(y).astype(X.dtype)
        for epoch in range(self.epochs):
            margin = y * (X @ self.w + self.b)
            coef = sw * y * (margin < 1)
            dw = self.w - self.C * (X.T @ coef) / n
            db = -self.C * float(coef.sum()) / n
            lr = self.lr / (1 + epoch / 1000)
            self.w -= (lr * dw).astype(X.dtype)
            self.b -= lr * db
            if self.verbose and (epoch + 1) % max(1, self.epochs // 4) == 0:
                print(f"    epoch {epoch + 1}/{self.epochs}, loss {self._loss(margin, sw):.4f}", flush=True)
        self.final_loss = self._loss(y * (X @ self.w + self.b), sw)
        return self

    def decision_function(self, X):
        return np.asarray(X) @ self.w + self.b

    def predict(self, X):
        return (self.decision_function(X) >= 0).astype(int)


class OneVsRestSVM:
    """One SVM per class (that class against the rest); the class with the highest score wins."""

    def __init__(self, **svm_params):
        self.params = svm_params
        self.classes_ = None
        self.models_ = []

    def fit(self, X, y):
        y = np.asarray(y)
        self.classes_ = sorted(set(y.tolist()))
        self.models_ = []
        for c in self.classes_:
            m = SVM(**self.params)
            if m.verbose:
                print(f"  class {c}:", flush=True)
            self.models_.append(m.fit(X, np.where(y == c, 1, -1)))
        return self

    def decision_function(self, X):
        return np.column_stack([m.decision_function(X) for m in self.models_])

    def predict(self, X):
        return [self.classes_[i] for i in self.decision_function(X).argmax(axis=1)]


class Pipeline:
    """Minimal pipeline: transformers (fit_transform / transform) followed by a final model.

    scikit-learn's own Pipeline insists on its estimator rules, which the notebook-style SVM
    deliberately does not follow.
    """

    def __init__(self, *models):
        self.steps = [(type(m).__name__, m) for m in models]

    def fit(self, X, y):
        for _, step in self.steps[:-1]:
            X = step.fit_transform(X, y)
        self.steps[-1][1].fit(X, y)
        return self

    def _transform(self, X):
        for _, step in self.steps[:-1]:
            X = step.transform(X)
        return X

    def predict(self, X):
        return self.steps[-1][1].predict(self._transform(X))

    def decision_function(self, X):
        return self.steps[-1][1].decision_function(self._transform(X))

    @property
    def classes_(self):
        return self.steps[-1][1].classes_
