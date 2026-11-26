from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import joblib

from app.core.exceptions import TrainingError
from app.ml.training import TrainingConfig, TrainingResult

POLL_INTERVAL_SECONDS = 0.5
TERMINATE_TIMEOUT_SECONDS = 2.0
BACKEND_ROOT = Path(__file__).resolve().parents[2]

# Preserve platform paths and numeric runtime settings. Dataset, database,
# broker, and artifact-store configuration stays in the supervising worker.
FIT_ENV = frozenset(
    {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "SYSTEMDRIVE",
        "USERPROFILE",
        "HOME",
        "TEMP",
        "TMP",
        "TMPDIR",
        "LD_LIBRARY_PATH",
        "CUDA_PATH",
        "CUDA_VISIBLE_DEVICES",
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    }
)


class FitProcessExited(ConnectionError):
    """A fit process disappeared without returning a training outcome."""


def _fit_command(directory: Path) -> list[str]:
    return [sys.executable, "-m", "app.workers.fit_worker", str(directory)]


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=TERMINATE_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def run_fit(
    dataset_path: Path,
    original_filename: str,
    algorithm: str,
    hyperparameters: dict[str, Any],
    config: TrainingConfig,
    *,
    check_active: Callable[[], None],
) -> TrainingResult:
    check_active()
    with tempfile.TemporaryDirectory(prefix="fit-", dir=dataset_path.parent) as temp:
        directory = Path(temp)
        (directory / "input.json").write_text(
            json.dumps(
                {
                    "dataset_path": str(dataset_path),
                    "original_filename": original_filename,
                    "algorithm": algorithm,
                    "hyperparameters": hyperparameters,
                    "config": asdict(config),
                }
            ),
            encoding="utf-8",
        )
        env = {key: value for key, value in os.environ.items() if key.upper() in FIT_ENV}
        env["PYTHONUTF8"] = "1"
        with subprocess.Popen(  # noqa: S603 - fixed interpreter and bundled module
            _fit_command(directory), cwd=BACKEND_ROOT, env=env, stdin=subprocess.PIPE
        ) as process:
            try:
                while True:
                    try:
                        process.wait(timeout=POLL_INTERVAL_SECONDS)
                    except subprocess.TimeoutExpired:
                        check_active()
                    else:
                        break
                check_active()
            finally:
                _stop(process)

        if process.returncode != 0:
            raise FitProcessExited(f"Model fit process exited with code {process.returncode}.")
        error_path = directory / "error.json"
        if error_path.is_file():
            error = json.loads(error_path.read_text(encoding="utf-8"))
            if error["retryable"]:
                raise ConnectionError(error["message"])
            raise TrainingError(error["message"])
        # Only the bundled fit process writes here, in a private directory.
        result_path = directory / "result.joblib"
        if not result_path.is_file():
            raise FitProcessExited("Model fit process did not return a result.")
        result: TrainingResult = joblib.load(result_path)
        check_active()
        return result
