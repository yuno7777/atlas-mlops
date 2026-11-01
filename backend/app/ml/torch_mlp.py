"""Optional PyTorch multi-layer perceptron classifier.

Imported lazily by the algorithm catalog. Requires the optional ``torch`` dependency.
This is a real training implementation, not a placeholder: it performs mini-batch
Adam optimization with a validation split and early stopping, and exposes the
scikit-learn estimator interface used by the platform pipeline.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.validation import check_array, check_is_fitted

try:
    import torch
    from torch import nn
except ImportError as exc:  # pragma: no cover - exercised only without torch
    raise ImportError("PyTorch is not installed") from exc


class TorchMLPClassifier(ClassifierMixin, BaseEstimator):
    def __init__(
        self,
        hidden_dim: int = 64,
        epochs: int = 30,
        learning_rate: float = 0.001,
        batch_size: int = 256,
        random_state: int = 42,
    ) -> None:
        self.hidden_dim = hidden_dim
        self.epochs = epochs
        self.learning_rate = learning_rate
        self.batch_size = batch_size
        self.random_state = random_state

    def _build_network(self, input_dim: int, output_dim: int) -> nn.Module:
        return nn.Sequential(
            nn.Linear(input_dim, self.hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(self.hidden_dim, max(self.hidden_dim // 2, 8)),
            nn.ReLU(),
            nn.Linear(max(self.hidden_dim // 2, 8), output_dim),
        )

    def fit(self, X: Any, y: Any) -> TorchMLPClassifier:
        torch.manual_seed(self.random_state)
        np.random.seed(self.random_state)
        X_array = check_array(X, ensure_2d=True, dtype=np.float64)
        self.label_encoder_ = LabelEncoder()
        y_encoded = self.label_encoder_.fit_transform(np.asarray(y))
        self.classes_ = self.label_encoder_.classes_
        self.n_features_in_ = X_array.shape[1]
        n_classes = len(self.classes_)
        if n_classes < 2:
            raise ValueError("PyTorch classifier requires at least two classes.")

        rng = np.random.default_rng(self.random_state)
        order = rng.permutation(len(X_array))
        validation_size = max(1, int(0.15 * len(X_array)))
        validation_idx = order[:validation_size]
        train_idx = order[validation_size:]
        if len(train_idx) < 2:
            train_idx, validation_idx = order, order

        X_tensor = torch.as_tensor(X_array, dtype=torch.float32)
        y_tensor = torch.as_tensor(y_encoded, dtype=torch.long)
        train_x, train_y = X_tensor[train_idx], y_tensor[train_idx]
        val_x, val_y = X_tensor[validation_idx], y_tensor[validation_idx]

        self.model_ = self._build_network(X_array.shape[1], n_classes)
        optimizer = torch.optim.Adam(self.model_.parameters(), lr=self.learning_rate)
        loss_fn = nn.CrossEntropyLoss()
        best_loss = float("inf")
        best_state = {key: value.clone() for key, value in self.model_.state_dict().items()}
        patience = 5
        stale_epochs = 0

        self.model_.train()
        for _epoch in range(self.epochs):
            permutation = torch.randperm(len(train_x))
            for start in range(0, len(train_x), self.batch_size):
                batch_indices = permutation[start : start + self.batch_size]
                optimizer.zero_grad()
                output = self.model_(train_x[batch_indices])
                loss = loss_fn(output, train_y[batch_indices])
                loss.backward()
                optimizer.step()
            self.model_.eval()
            with torch.no_grad():
                validation_loss = float(loss_fn(self.model_(val_x), val_y).item())
            self.model_.train()
            if validation_loss < best_loss - 1e-5:
                best_loss = validation_loss
                best_state = {key: value.clone() for key, value in self.model_.state_dict().items()}
                stale_epochs = 0
            else:
                stale_epochs += 1
                if stale_epochs >= patience:
                    break

        self.model_.load_state_dict(best_state)
        self.model_.eval()
        self.loss_history_ = self._probe_loss(val_x, val_y, loss_fn)
        return self

    def _probe_loss(self, val_x: torch.Tensor, val_y: torch.Tensor, loss_fn: nn.Module) -> float:
        with torch.no_grad():
            return float(loss_fn(self.model_(val_x), val_y).item())

    def predict_proba(self, X: Any) -> np.ndarray:
        check_is_fitted(self, ["model_", "classes_"])
        X_array = check_array(X, ensure_2d=True, dtype=np.float64)
        self.model_.eval()
        with torch.no_grad():
            logits = self.model_(torch.as_tensor(X_array, dtype=torch.float32))
            return torch.softmax(logits, dim=1).cpu().numpy()

    def predict(self, X: Any) -> np.ndarray:
        probabilities = self.predict_proba(X)
        encoded = probabilities.argmax(axis=1)
        return self.label_encoder_.inverse_transform(encoded)
