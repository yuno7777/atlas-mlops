from __future__ import annotations

import io
import os
import threading
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JOB_EXECUTION_MODE", "sync")
os.environ.setdefault("MLFLOW_ENABLED", "false")
os.environ.setdefault("ENABLE_MONITORING_SCHEDULER", "false")


class _AlertReceiver(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.send_response(204)
        self.end_headers()

    def log_message(self, _format: str, *_args: object) -> None:
        return


def main() -> None:
    import uvicorn
    from alembic.config import Config

    from alembic import command

    backend_dir = Path(__file__).resolve().parent
    root_dir = backend_dir.parent
    config = Config(str(backend_dir / "alembic.ini"))
    command.upgrade(config, "head")

    from app.cli import main as cli_main

    # The seed command prints the one-time API key. Keep it out of CI logs.
    with redirect_stdout(io.StringIO()):
        result = cli_main(
            [
                "seed-demo",
                "--data-file",
                str(root_dir / "demo-data" / "customer_churn.csv"),
            ]
        )
    if result != 0:
        raise RuntimeError("Could not seed the browser-test database.")

    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.registry import ModelVersion, RegisteredModel
    from app.models.training import Experiment
    from app.services.registry import register_experiment_as_model

    with SessionLocal() as db:
        model = db.scalar(select(RegisteredModel).where(RegisteredModel.name == "Churn Propensity"))
        if model is None:
            raise RuntimeError("The browser-test seed did not register a model.")
        versions = list(
            db.scalars(
                select(ModelVersion).where(ModelVersion.registered_model_id == model.id)
            ).all()
        )
        if len(versions) < 2:
            registered_experiments = {version.experiment_id for version in versions}
            candidate = db.scalar(
                select(Experiment)
                .where(
                    Experiment.project_id == model.project_id,
                    Experiment.status == "completed",
                    Experiment.id.not_in(registered_experiments),
                )
                .order_by(Experiment.created_at.asc())
            )
            if candidate is None:
                raise RuntimeError("The browser-test seed has no second completed experiment.")
            register_experiment_as_model(
                db,
                experiment_id=candidate.id,
                user_id=model.created_by,
                model_name=model.name,
                model_id=model.id,
                add_to_existing=True,
            )

    alert_port = int(os.environ.get("ATLAS_E2E_ALERT_PORT", "8011"))
    alert_server = ThreadingHTTPServer(("127.0.0.1", alert_port), _AlertReceiver)
    threading.Thread(target=alert_server.serve_forever, daemon=True).start()

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=int(os.environ.get("ATLAS_E2E_API_PORT", "8010")),
        log_level="warning",
    )


if __name__ == "__main__":
    main()
