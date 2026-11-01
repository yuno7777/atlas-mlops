from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import shutil
import tempfile
from collections.abc import Generator, Iterator
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Protocol

from app.core.config import get_settings
from app.core.exceptions import NotFoundError, ServiceUnavailableError

logger = logging.getLogger(__name__)
CHUNK_SIZE = 1024 * 1024


def _validate_key(key: str) -> str:
    if not key or key.startswith("/") or "\\" in key:
        raise ValueError("Invalid storage key")
    path = PurePosixPath(key)
    if ".." in path.parts:
        raise ValueError("Invalid storage key")
    return str(path)


class StorageBackend(Protocol):
    backend_name: str

    def put_file(self, key: str, source: Path) -> None: ...
    def put_bytes(self, key: str, data: bytes) -> None: ...
    def read_bytes(self, key: str) -> bytes: ...
    def sha256(self, key: str) -> str: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def delete_prefix(self, prefix: str) -> None: ...
    def iter_chunks(self, key: str) -> Iterator[bytes]: ...
    def open_path(self, key: str) -> contextlib.AbstractContextManager[Path]: ...
    def health(self) -> tuple[bool, str]: ...


class LocalStorage:
    backend_name = "local"

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        safe_key = _validate_key(key)
        path = (self.root / safe_key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Storage key escapes the artifact root")
        return path

    def put_file(self, key: str, source: Path) -> None:
        destination = self._resolve(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_path = destination.with_suffix(destination.suffix + ".tmp")
        shutil.copyfile(source, temp_path)
        temp_path.replace(destination)

    def put_bytes(self, key: str, data: bytes) -> None:
        destination = self._resolve(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_path = destination.with_suffix(destination.suffix + ".tmp")
        temp_path.write_bytes(data)
        temp_path.replace(destination)

    def read_bytes(self, key: str) -> bytes:
        path = self._resolve(key)
        if not path.is_file():
            raise NotFoundError(f"Artifact not found: {key}")
        return path.read_bytes()

    def sha256(self, key: str) -> str:
        path = self._resolve(key)
        if not path.is_file():
            raise NotFoundError(f"Artifact not found: {key}")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def exists(self, key: str) -> bool:
        try:
            return self._resolve(key).is_file()
        except ValueError:
            return False

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        path.unlink(missing_ok=True)

    def delete_prefix(self, prefix: str) -> None:
        safe_prefix = _validate_key(prefix.rstrip("/"))
        target = self._resolve(safe_prefix)
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)

    def iter_chunks(self, key: str) -> Iterator[bytes]:
        path = self._resolve(key)
        if not path.is_file():
            raise NotFoundError(f"Artifact not found: {key}")
        with path.open("rb") as handle:
            yield from iter(lambda: handle.read(CHUNK_SIZE), b"")

    @contextlib.contextmanager
    def open_path(self, key: str) -> Generator[Path, None, None]:
        path = self._resolve(key)
        if not path.is_file():
            raise NotFoundError(f"Artifact not found: {key}")
        yield path

    def health(self) -> tuple[bool, str]:
        try:
            probe = self.root / ".health"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return True, str(self.root)
        except OSError as exc:
            return False, f"Artifact root is not writable: {exc}"


class S3Storage:
    backend_name = "s3"

    def __init__(self) -> None:
        import boto3

        settings = get_settings()
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            region_name=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.s3_access_key_id or None,
            aws_secret_access_key=settings.s3_secret_access_key or None,
            use_ssl=settings.s3_use_ssl,
        )

    def put_file(self, key: str, source: Path) -> None:
        self.client.upload_file(str(source), self.bucket, _validate_key(key))

    def put_bytes(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=_validate_key(key), Body=data)

    def read_bytes(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=_validate_key(key))
        except self.client.exceptions.NoSuchKey as exc:
            raise NotFoundError(f"Artifact not found: {key}") from exc
        return response["Body"].read()

    def sha256(self, key: str) -> str:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=_validate_key(key))
        except self.client.exceptions.NoSuchKey as exc:
            raise NotFoundError(f"Artifact not found: {key}") from exc
        digest = hashlib.sha256()
        for chunk in response["Body"].iter_chunks(chunk_size=CHUNK_SIZE):
            digest.update(chunk)
        return digest.hexdigest()

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=_validate_key(key))
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=_validate_key(key))

    def delete_prefix(self, prefix: str) -> None:
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(
            Bucket=self.bucket, Prefix=_validate_key(prefix.rstrip("/"))
        ):
            contents = page.get("Contents", [])
            if contents:
                self.client.delete_objects(
                    Bucket=self.bucket,
                    Delete={"Objects": [{"Key": item["Key"]} for item in contents]},
                )

    def iter_chunks(self, key: str) -> Iterator[bytes]:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=_validate_key(key))
        except self.client.exceptions.NoSuchKey as exc:
            raise NotFoundError(f"Artifact not found: {key}") from exc
        yield from response["Body"].iter_chunks(chunk_size=CHUNK_SIZE)

    @contextlib.contextmanager
    def open_path(self, key: str) -> Generator[Path, None, None]:
        suffix = Path(key).suffix or ".bin"
        file_descriptor, temp_name = tempfile.mkstemp(suffix=suffix)
        temp_path = Path(temp_name)
        os.close(file_descriptor)
        try:
            self.client.download_file(self.bucket, _validate_key(key), str(temp_path))
            yield temp_path
        finally:
            temp_path.unlink(missing_ok=True)

    def health(self) -> tuple[bool, str]:
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return True, f"s3://{self.bucket}"
        except Exception as exc:
            return False, f"S3 bucket unavailable: {exc}"


@lru_cache
def get_storage() -> StorageBackend:
    settings = get_settings()
    if settings.storage_backend == "s3":
        try:
            return S3Storage()
        except Exception as exc:
            logger.exception("Failed to initialize S3 storage")
            raise ServiceUnavailableError(f"Object storage is not available: {exc}") from exc
    return LocalStorage(settings.artifact_root)


def dataset_key(dataset_id: str, version: int, checksum: str, extension: str) -> str:
    extension = extension if extension.startswith(".") else f".{extension}"
    return f"datasets/{dataset_id}/v{version}/{checksum[:16]}{extension}"


def training_artifact_prefix(job_id: str, experiment_id: str) -> str:
    return f"training/{job_id}/{experiment_id}"


def registry_artifact_prefix(model_id: str, version: int) -> str:
    return f"registry/{model_id}/v{version}"
