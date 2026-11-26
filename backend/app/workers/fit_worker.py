"""Private subprocess entry point for a single model fit."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from threading import Thread

logger = logging.getLogger(__name__)


def _watch_parent() -> None:
    # The supervisor is the only writer. If it dies, the pipe closes even when
    # Celery or the OS killed it before Python could run a finally block.
    os.read(sys.stdin.fileno(), 1)
    os._exit(2)


def main() -> None:
    Thread(target=_watch_parent, daemon=True, name="atlas-fit-parent-watch").start()

    import joblib

    from app.core.exceptions import DatasetValidationError, TrainingError
    from app.ml.algorithms import get_algorithm
    from app.ml.training import TrainingConfig, train_algorithm
    from app.ml.validation import read_dataframe

    directory = Path(sys.argv[1])
    request = json.loads((directory / "input.json").read_text(encoding="utf-8"))
    try:
        frame = read_dataframe(Path(request["dataset_path"]), request["original_filename"])
        config = TrainingConfig(**request["config"])
        spec = get_algorithm(request["algorithm"], config.problem_type)
        # Keep joblib pools inside the fit process so stopping the process also
        # stops native libraries and parallel model fitting.
        with joblib.parallel_config(backend="threading"):
            result = train_algorithm(frame, spec, request["hyperparameters"], config)
            joblib.dump(result, directory / "result.joblib")
    except Exception as exc:
        retryable = isinstance(exc, (ConnectionError, TimeoutError)) or isinstance(
            exc.__cause__, (ConnectionError, TimeoutError)
        )
        message = str(exc) if isinstance(exc, (DatasetValidationError, TrainingError)) else ""
        if not message:
            logger.exception("Model fit subprocess failed")
            message = "Model fitting failed in the subprocess."
        (directory / "error.json").write_text(
            json.dumps({"message": message[:4000], "retryable": retryable}),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
