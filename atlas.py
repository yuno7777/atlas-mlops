# ruff: noqa: S603

"""Run the Atlas developer workflow from a Windows or Linux checkout."""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.client import HTTPConnection, HTTPException
from pathlib import Path

from scripts.compose_smoke import run_lifecycle

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
PYTHON = BACKEND / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
VITE = FRONTEND / "node_modules/vite/bin/vite.js"
LOOPBACK = "127.0.0.1"


def executable(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(f"{name} is missing from PATH. See the native quickstart in README.md.")
    return path


def npm() -> str:
    return executable("npm.cmd" if os.name == "nt" else "npm")


def installed_python() -> str:
    if not PYTHON.is_file():
        raise RuntimeError("Atlas dependencies are missing. Run python -m atlas setup.")
    return str(PYTHON)


def setup(_args: argparse.Namespace) -> None:
    uv = executable("uv")
    npm_command = npm()
    subprocess.run(
        [uv, "venv", "--allow-existing", "--python", "3.12", ".venv"], cwd=BACKEND, check=True
    )
    python = installed_python()
    subprocess.run(
        [uv, "pip", "sync", "--python", python, "--require-hashes", "requirements.lock"],
        cwd=BACKEND,
        check=True,
    )
    subprocess.run(
        [
            uv,
            "pip",
            "install",
            "--python",
            python,
            "-c",
            "requirements.lock",
            "-r",
            "requirements-dev.txt",
        ],
        cwd=BACKEND,
        check=True,
    )
    subprocess.run([npm_command, "ci"], cwd=FRONTEND, check=True)


def native_environment(data_dir: Path) -> dict[str, str]:
    data_dir = data_dir.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    return {
        **os.environ,
        "ENVIRONMENT": "development",
        "DATABASE_URL": f"sqlite:///{(data_dir / 'atlas.db').as_posix()}",
        "ARTIFACT_ROOT": str(data_dir / "artifacts"),
        "STORAGE_BACKEND": "local",
        "JOB_EXECUTION_MODE": "thread",
        "THREAD_WORKERS": "1",
        "SECRET_KEY": secrets.token_hex(32),
        "ALLOW_REGISTRATION": "true",
        "DOCS_ENABLED": "true",
        "MLFLOW_ENABLED": "false",
        "ENABLE_MONITORING_SCHEDULER": "false",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
    }


def migrate(python: str, env: dict[str, str]) -> None:
    subprocess.run([python, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True)


def api_command(python: str, port: int) -> list[str]:
    return [
        python,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        LOOPBACK,
        "--port",
        str(port),
        "--timeout-graceful-shutdown",
        "10",
    ]


@contextmanager
def background_process(
    command: list[str], directory: Path, env: dict[str, str]
) -> Iterator[subprocess.Popen]:
    process = subprocess.Popen(
        command,
        cwd=directory,
        env=env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    try:
        yield process
    finally:
        if process.poll() is None:
            try:
                if os.name == "nt":
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    process.terminate()
            except OSError:
                process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def wait_http(process: subprocess.Popen, port: int, path: str) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Service on port {port} exited with code {process.returncode}.")
        connection = HTTPConnection(LOOPBACK, port, timeout=1)
        try:
            connection.request("GET", path)
            with connection.getresponse() as response:
                if response.status == 200:
                    return
        except (OSError, HTTPException):
            pass
        finally:
            connection.close()
        time.sleep(0.2)
    raise RuntimeError(f"Service did not become ready on http://{LOOPBACK}:{port}{path}.")


def parse_port(value: str) -> int:
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("expected a TCP port from 1 to 65535")
    return port


def check_port(port: int) -> None:
    with socket.socket() as listener:
        try:
            listener.bind((LOOPBACK, port))
        except OSError as exc:
            raise RuntimeError(
                f"Port {port} is unavailable on {LOOPBACK}. Choose another port."
            ) from exc


def doctor(args: argparse.Namespace) -> None:
    for command in (
        [executable("uv"), "--version"],
        [executable("node"), "--version"],
        [npm(), "--version"],
    ):
        subprocess.run(command, check=True)
    python = installed_python()
    subprocess.run(
        [
            python,
            "-c",
            "import alembic, sklearn, uvicorn; import sys; assert sys.version_info[:2] == (3, 12)",
        ],
        check=True,
    )
    if not VITE.is_file():
        raise RuntimeError("Frontend dependencies are missing. Run python -m atlas setup.")
    args.data_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=args.data_dir) as probe:
        probe.write(b"Atlas")
    database = args.data_dir / "atlas.db"
    if database.is_file():
        try:
            subprocess.run(
                [python, "-m", "alembic", "current", "--check-heads"],
                cwd=BACKEND,
                env=native_environment(args.data_dir),
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "Database migration check failed. Run atlas serve or dev to apply migrations."
            ) from exc
    else:
        print("A new SQLite database will be created by serve or dev.")
    check_port(args.api_port)
    check_port(args.ui_port)
    print(f"Native dependencies, data directory, and ports are ready ({args.data_dir.resolve()}).")


def serve(args: argparse.Namespace) -> None:
    python = installed_python()
    check_port(args.api_port)
    env = native_environment(args.data_dir)
    migrate(python, env)
    subprocess.run(api_command(python, args.api_port), cwd=BACKEND, env=env, check=True)


def dev(args: argparse.Namespace) -> None:
    python = installed_python()
    node = executable("node")
    if not VITE.is_file():
        raise RuntimeError("Frontend dependencies are missing. Run python -m atlas setup.")
    if args.api_port == args.ui_port:
        raise RuntimeError("The API and UI require different ports.")
    check_port(args.api_port)
    check_port(args.ui_port)
    env = native_environment(args.data_dir)
    env["ATLAS_API_PROXY_TARGET"] = f"http://{LOOPBACK}:{args.api_port}"
    migrate(python, env)
    subprocess.run([npm(), "run", "build"], cwd=FRONTEND, env=env, check=True)
    frontend = [
        node,
        str(VITE),
        "preview",
        "--host",
        LOOPBACK,
        "--port",
        str(args.ui_port),
        "--strictPort",
    ]
    with (
        background_process(api_command(python, args.api_port), BACKEND, env) as api,
        background_process(frontend, FRONTEND, env) as ui,
    ):
        wait_http(api, args.api_port, "/ready")
        wait_http(ui, args.ui_port, "/")
        print(
            f"Atlas UI is ready at http://{LOOPBACK}:{args.ui_port}. Press Ctrl+C to stop.",
            flush=True,
        )
        while api.poll() is None and ui.poll() is None:
            time.sleep(0.5)
        raise RuntimeError("An Atlas service stopped. Review its output above.")


def seed_demo(args: argparse.Namespace) -> None:
    python = installed_python()
    env = native_environment(args.data_dir)
    env["JOB_EXECUTION_MODE"] = "sync"
    migrate(python, env)
    subprocess.run([python, "-m", "app.cli", "seed-demo"], cwd=BACKEND, env=env, check=True)


def test(_args: argparse.Namespace) -> None:
    subprocess.run([installed_python(), "-m", "pytest"], cwd=BACKEND, check=True)


def train_smoke(_args: argparse.Namespace) -> None:
    python = installed_python()
    with socket.socket() as listener:
        listener.bind((LOOPBACK, 0))
        port = listener.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="Atlas café ") as directory:
        env = native_environment(Path(directory))
        migrate(python, env)
        with background_process(api_command(python, port), BACKEND, env) as api:
            wait_http(api, port, "/ready")
            run_lifecycle(port=port, execution_mode="thread")


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m atlas", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, description, handler in (
        ("setup", "Install locked Python and Node dependencies", setup),
        ("doctor", "Check the toolchain, data directory, and ports", doctor),
        ("serve", "Migrate the database and start the native API", serve),
        ("dev", "Start the native API and built UI", dev),
        ("test", "Run the backend test suite", test),
        ("seed-demo", "Seed a local demo account, dataset, and deployment", seed_demo),
        (
            "train-smoke",
            "Train, register, and serve a tiny model through a native API",
            train_smoke,
        ),
    ):
        command = commands.add_parser(name, help=description)
        command.set_defaults(handler=handler)
        if name in {"doctor", "serve", "dev", "seed-demo"}:
            command.add_argument("--data-dir", type=Path, default=BACKEND / "data")
        if name in {"doctor", "serve", "dev"}:
            command.add_argument("--api-port", type=parse_port, default=8000)
        if name in {"doctor", "dev"}:
            command.add_argument("--ui-port", type=parse_port, default=5173)
    args = parser.parse_args()
    try:
        args.handler(args)
    except KeyboardInterrupt:
        return 130
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Atlas: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
