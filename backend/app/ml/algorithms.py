from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from sklearn.base import BaseEstimator
from sklearn.cluster import DBSCAN, KMeans
from sklearn.ensemble import (
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC, SVR
from sklearn.tree import DecisionTreeClassifier

from app.core.exceptions import ValidationError
from app.models.enums import ProblemType

HyperparameterType = Literal["int", "float", "choice", "bool"]


@dataclass(frozen=True)
class Hyperparameter:
    name: str
    label: str
    type: HyperparameterType
    default: Any
    description: str = ""
    min: float | None = None
    max: float | None = None
    step: float | None = None
    choices: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "type": self.type,
            "default": self.default,
            "min": self.min,
            "max": self.max,
            "step": self.step,
            "choices": self.choices,
            "description": self.description,
        }


@dataclass(frozen=True)
class AlgorithmSpec:
    id: str
    label: str
    problem_type: str
    description: str
    framework: str
    build: Callable[[dict[str, Any]], BaseEstimator]
    hyperparameters: list[Hyperparameter] = field(default_factory=list)
    supports_cv: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "problem_type": self.problem_type,
            "description": self.description,
            "framework": self.framework,
            "supports_cv": self.supports_cv,
            "hyperparameters": [
                hyperparameter.to_dict() for hyperparameter in self.hyperparameters
            ],
        }


def _hp(
    name: str, label: str, type_: HyperparameterType, default: Any, **kwargs: Any
) -> Hyperparameter:
    return Hyperparameter(name=name, label=label, type=type_, default=default, **kwargs)


CLASSIFICATION: list[AlgorithmSpec] = [
    AlgorithmSpec(
        id="logistic_regression",
        label="Logistic Regression",
        problem_type=ProblemType.CLASSIFICATION,
        description="Linear model for binary and multiclass classification.",
        framework="scikit-learn",
        hyperparameters=[
            _hp("C", "Regularization strength", "float", 1.0, min=0.001, max=100, step=0.1),
            _hp("max_iter", "Maximum iterations", "int", 500, min=100, max=5000, step=100),
            _hp("class_weight", "Class weight", "choice", "none", choices=["none", "balanced"]),
        ],
        build=lambda params: LogisticRegression(
            C=params["C"],
            max_iter=params["max_iter"],
            class_weight=None if params["class_weight"] == "none" else "balanced",
            solver="lbfgs",
        ),
    ),
    AlgorithmSpec(
        id="random_forest_classifier",
        label="Random Forest",
        problem_type=ProblemType.CLASSIFICATION,
        description="Bagged decision trees with strong tabular performance.",
        framework="scikit-learn",
        hyperparameters=[
            _hp("n_estimators", "Number of trees", "int", 200, min=10, max=1000, step=10),
            _hp("max_depth", "Maximum depth", "int", 12, min=1, max=100, step=1),
            _hp("min_samples_split", "Minimum samples to split", "int", 2, min=2, max=100, step=1),
        ],
        build=lambda params: RandomForestClassifier(
            n_estimators=params["n_estimators"],
            max_depth=params["max_depth"],
            min_samples_split=params["min_samples_split"],
            n_jobs=-1,
            random_state=params.get("_seed", 42),
        ),
    ),
    AlgorithmSpec(
        id="decision_tree_classifier",
        label="Decision Tree",
        problem_type=ProblemType.CLASSIFICATION,
        description="Interpretable single-tree baseline.",
        framework="scikit-learn",
        hyperparameters=[
            _hp("max_depth", "Maximum depth", "int", 8, min=1, max=100, step=1),
            _hp("min_samples_split", "Minimum samples to split", "int", 2, min=2, max=100, step=1),
        ],
        build=lambda params: DecisionTreeClassifier(
            max_depth=params["max_depth"],
            min_samples_split=params["min_samples_split"],
            random_state=params.get("_seed", 42),
        ),
    ),
    AlgorithmSpec(
        id="gradient_boosting_classifier",
        label="Gradient Boosting",
        problem_type=ProblemType.CLASSIFICATION,
        description="Sequential boosted trees.",
        framework="scikit-learn",
        hyperparameters=[
            _hp("n_estimators", "Boosting rounds", "int", 150, min=10, max=500, step=10),
            _hp("learning_rate", "Learning rate", "float", 0.1, min=0.001, max=1.0, step=0.01),
            _hp("max_depth", "Maximum depth", "int", 3, min=1, max=20, step=1),
        ],
        build=lambda params: GradientBoostingClassifier(
            n_estimators=params["n_estimators"],
            learning_rate=params["learning_rate"],
            max_depth=params["max_depth"],
            random_state=params.get("_seed", 42),
        ),
    ),
    AlgorithmSpec(
        id="svm_classifier",
        label="Support Vector Machine",
        problem_type=ProblemType.CLASSIFICATION,
        description="Margin-based classifier with RBF/linear kernels.",
        framework="scikit-learn",
        hyperparameters=[
            _hp("C", "Regularization", "float", 1.0, min=0.01, max=100, step=0.1),
            _hp("kernel", "Kernel", "choice", "rbf", choices=["rbf", "linear"]),
            _hp("gamma", "Kernel coefficient", "choice", "scale", choices=["scale", "auto"]),
        ],
        build=lambda params: SVC(
            C=params["C"],
            kernel=params["kernel"],
            gamma=params["gamma"],
            probability=True,
            random_state=params.get("_seed", 42),
        ),
    ),
    AlgorithmSpec(
        id="knn_classifier",
        label="K-Nearest Neighbors",
        problem_type=ProblemType.CLASSIFICATION,
        description="Distance-based instance learner.",
        framework="scikit-learn",
        hyperparameters=[
            _hp("n_neighbors", "Neighbors", "int", 5, min=1, max=50, step=1),
            _hp(
                "weights",
                "Neighbor weighting",
                "choice",
                "uniform",
                choices=["uniform", "distance"],
            ),
        ],
        build=lambda params: KNeighborsClassifier(
            n_neighbors=params["n_neighbors"], weights=params["weights"]
        ),
    ),
]

REGRESSION: list[AlgorithmSpec] = [
    AlgorithmSpec(
        id="linear_regression",
        label="Linear Regression",
        problem_type=ProblemType.REGRESSION,
        description="Ordinary least squares baseline.",
        framework="scikit-learn",
        hyperparameters=[
            _hp("fit_intercept", "Fit intercept", "bool", True),
        ],
        build=lambda params: LinearRegression(fit_intercept=params["fit_intercept"]),
    ),
    AlgorithmSpec(
        id="ridge_regression",
        label="Ridge Regression",
        problem_type=ProblemType.REGRESSION,
        description="L2-regularized linear regression.",
        framework="scikit-learn",
        hyperparameters=[
            _hp("alpha", "Regularization strength", "float", 1.0, min=0.000001, max=1000, step=0.1),
        ],
        build=lambda params: Ridge(alpha=params["alpha"], random_state=params.get("_seed", 42)),
    ),
    AlgorithmSpec(
        id="random_forest_regressor",
        label="Random Forest",
        problem_type=ProblemType.REGRESSION,
        description="Bagged regression trees.",
        framework="scikit-learn",
        hyperparameters=[
            _hp("n_estimators", "Number of trees", "int", 200, min=10, max=1000, step=10),
            _hp("max_depth", "Maximum depth", "int", 12, min=1, max=100, step=1),
            _hp("min_samples_split", "Minimum samples to split", "int", 2, min=2, max=100, step=1),
        ],
        build=lambda params: RandomForestRegressor(
            n_estimators=params["n_estimators"],
            max_depth=params["max_depth"],
            min_samples_split=params["min_samples_split"],
            n_jobs=-1,
            random_state=params.get("_seed", 42),
        ),
    ),
    AlgorithmSpec(
        id="gradient_boosting_regressor",
        label="Gradient Boosting",
        problem_type=ProblemType.REGRESSION,
        description="Sequential boosted regression trees.",
        framework="scikit-learn",
        hyperparameters=[
            _hp("n_estimators", "Boosting rounds", "int", 150, min=10, max=500, step=10),
            _hp("learning_rate", "Learning rate", "float", 0.1, min=0.001, max=1.0, step=0.01),
            _hp("max_depth", "Maximum depth", "int", 3, min=1, max=20, step=1),
        ],
        build=lambda params: GradientBoostingRegressor(
            n_estimators=params["n_estimators"],
            learning_rate=params["learning_rate"],
            max_depth=params["max_depth"],
            random_state=params.get("_seed", 42),
        ),
    ),
    AlgorithmSpec(
        id="svr",
        label="Support Vector Regression",
        problem_type=ProblemType.REGRESSION,
        description="Margin-based regression.",
        framework="scikit-learn",
        hyperparameters=[
            _hp("C", "Regularization", "float", 1.0, min=0.01, max=100, step=0.1),
            _hp("epsilon", "Epsilon tube", "float", 0.1, min=0.001, max=10, step=0.01),
            _hp("kernel", "Kernel", "choice", "rbf", choices=["rbf", "linear"]),
        ],
        build=lambda params: SVR(
            C=params["C"],
            epsilon=params["epsilon"],
            kernel=params["kernel"],
            gamma="scale",
        ),
    ),
]

CLUSTERING: list[AlgorithmSpec] = [
    AlgorithmSpec(
        id="kmeans",
        label="K-Means",
        problem_type=ProblemType.CLUSTERING,
        description="Centroid-based partitioning.",
        framework="scikit-learn",
        hyperparameters=[
            _hp("n_clusters", "Clusters", "int", 4, min=2, max=50, step=1),
            _hp("n_init", "Initializations", "int", 10, min=1, max=50, step=1),
        ],
        supports_cv=False,
        build=lambda params: KMeans(
            n_clusters=params["n_clusters"],
            n_init=params["n_init"],
            random_state=params.get("_seed", 42),
        ),
    ),
    AlgorithmSpec(
        id="dbscan",
        label="DBSCAN",
        problem_type=ProblemType.CLUSTERING,
        description="Density-based clustering that discovers arbitrary shapes and noise.",
        framework="scikit-learn",
        hyperparameters=[
            _hp("eps", "Neighborhood radius", "float", 0.5, min=0.01, max=100, step=0.05),
            _hp("min_samples", "Minimum samples", "int", 5, min=2, max=100, step=1),
        ],
        supports_cv=False,
        build=lambda params: DBSCAN(eps=params["eps"], min_samples=params["min_samples"]),
    ),
]


def _register_torch() -> None:
    try:
        from app.ml.torch_mlp import TorchMLPClassifier

        CLASSIFICATION.append(
            AlgorithmSpec(
                id="mlp_torch",
                label="PyTorch MLP",
                problem_type=ProblemType.CLASSIFICATION,
                description="Feed-forward neural network trained with Adam (optional dependency).",
                framework="pytorch",
                hyperparameters=[
                    _hp("hidden_dim", "Hidden units", "int", 64, min=8, max=512, step=8),
                    _hp("epochs", "Epochs", "int", 30, min=1, max=200, step=1),
                    _hp(
                        "learning_rate",
                        "Learning rate",
                        "float",
                        0.001,
                        min=0.00001,
                        max=0.1,
                        step=0.0001,
                    ),
                ],
                build=lambda params: TorchMLPClassifier(
                    hidden_dim=params["hidden_dim"],
                    epochs=params["epochs"],
                    learning_rate=params["learning_rate"],
                    random_state=params.get("_seed", 42),
                ),
            )
        )
    except ImportError:
        pass


_register_torch()

ALL_ALGORITHMS: list[AlgorithmSpec] = CLASSIFICATION + REGRESSION + CLUSTERING
_BY_ID: dict[str, AlgorithmSpec] = {spec.id: spec for spec in ALL_ALGORITHMS}


def list_algorithms(problem_type: str | None = None) -> list[AlgorithmSpec]:
    if problem_type:
        return [spec for spec in ALL_ALGORITHMS if spec.problem_type == problem_type]
    return list(ALL_ALGORITHMS)


def get_algorithm(algorithm_id: str, problem_type: str) -> AlgorithmSpec:
    spec = _BY_ID.get(algorithm_id)
    if spec is None:
        raise ValidationError(f"Unknown algorithm '{algorithm_id}'.")
    if spec.problem_type != problem_type:
        raise ValidationError(
            f"Algorithm '{algorithm_id}' supports {spec.problem_type}, not {problem_type}."
        )
    return spec


def validate_hyperparameters(spec: AlgorithmSpec, provided: dict[str, Any]) -> dict[str, Any]:
    allowed = {hyperparameter.name for hyperparameter in spec.hyperparameters}
    unknown = sorted(set(provided) - allowed)
    if unknown:
        raise ValidationError(
            f"Unknown hyperparameters for {spec.id}: {', '.join(unknown)}",
            details=[
                {"field": f"hyperparameters.{name}", "message": "Unknown hyperparameter"}
                for name in unknown
            ],
        )
    values: dict[str, Any] = {}
    for hyperparameter in spec.hyperparameters:
        value = provided.get(hyperparameter.name, hyperparameter.default)
        if hyperparameter.type == "int":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValidationError(f"{spec.id}.{hyperparameter.name} must be an integer.")
            if int(value) != value:
                raise ValidationError(f"{spec.id}.{hyperparameter.name} must be an integer.")
            value = int(value)
        elif hyperparameter.type == "float":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValidationError(f"{spec.id}.{hyperparameter.name} must be numeric.")
            value = float(value)
        elif hyperparameter.type == "bool":
            if not isinstance(value, bool):
                raise ValidationError(f"{spec.id}.{hyperparameter.name} must be a boolean.")
        elif hyperparameter.type == "choice":
            if value not in (hyperparameter.choices or []):
                choices = ", ".join(hyperparameter.choices or [])
                raise ValidationError(f"{spec.id}.{hyperparameter.name} must be one of: {choices}")
        if (
            hyperparameter.min is not None
            and isinstance(value, (int, float))
            and value < hyperparameter.min
        ):
            raise ValidationError(
                f"{spec.id}.{hyperparameter.name} must be >= {hyperparameter.min}."
            )
        if (
            hyperparameter.max is not None
            and isinstance(value, (int, float))
            and value > hyperparameter.max
        ):
            raise ValidationError(
                f"{spec.id}.{hyperparameter.name} must be <= {hyperparameter.max}."
            )
        values[hyperparameter.name] = value
    return values


def build_estimator(
    spec: AlgorithmSpec, hyperparameters: dict[str, Any], seed: int
) -> BaseEstimator:
    values = validate_hyperparameters(spec, hyperparameters)
    values["_seed"] = seed
    return spec.build(values)
