"""Artifact store.

Application code only depends on the `ArtifactStore` protocol. The S3 implementation
uses the generic S3 API (works with any S3-compatible object store: RustFS, Garage,
SeaweedFS, MinIO, AWS S3). The local implementation is used by tests and the CLI.

Keys are always built from validated identifiers (`runs/<run_id>/<artifact-name>`),
so user-controlled names cannot escape the run prefix.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from reslab_core.ids import validate_artifact_name, validate_run_id
from reslab_platform.logging import get_logger
from reslab_platform.settings import PlatformSettings

log = get_logger(__name__)


@dataclass(frozen=True)
class StoredArtifact:
    key: str
    size_bytes: int
    sha256: str
    content_type: str


def artifact_key(run_id: str, name: str) -> str:
    return f"runs/{validate_run_id(run_id)}/{validate_artifact_name(name)}"


@runtime_checkable
class ArtifactStore(Protocol):
    async def ensure_ready(self) -> None: ...

    async def put(
        self, run_id: str, name: str, data: bytes, content_type: str
    ) -> StoredArtifact: ...

    async def get(self, run_id: str, name: str) -> bytes: ...

    async def exists(self, run_id: str, name: str) -> bool: ...

    async def list(self, run_id: str) -> list[str]: ...

    def describe(self) -> str: ...


class LocalArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, run_id: str, name: str) -> Path:
        key = artifact_key(run_id, name)
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("artifact path escapes the store root")
        return path

    async def ensure_ready(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    async def put(self, run_id: str, name: str, data: bytes, content_type: str) -> StoredArtifact:
        path = self._path(run_id, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)
        return StoredArtifact(
            key=artifact_key(run_id, name),
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            content_type=content_type,
        )

    async def get(self, run_id: str, name: str) -> bytes:
        return await asyncio.to_thread(self._path(run_id, name).read_bytes)

    async def exists(self, run_id: str, name: str) -> bool:
        return self._path(run_id, name).exists()

    async def list(self, run_id: str) -> list[str]:
        folder = self.root / "runs" / validate_run_id(run_id)
        if not folder.exists():
            return []
        return sorted(p.name for p in folder.iterdir() if p.is_file())

    def describe(self) -> str:
        return f"local:{self.root}"


class S3ArtifactStore:
    def __init__(
        self,
        *,
        endpoint_url: str,
        region: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        force_path_style: bool = True,
    ) -> None:
        import boto3
        from botocore.config import Config

        self.bucket = bucket
        self.endpoint_url = endpoint_url
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(
                s3={"addressing_style": "path" if force_path_style else "auto"},
                retries={"max_attempts": 4, "mode": "standard"},
                connect_timeout=5,
                read_timeout=30,
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )

    async def ensure_ready(self) -> None:
        def _ensure() -> None:
            from botocore.exceptions import ClientError

            try:
                self._client.head_bucket(Bucket=self.bucket)
            except ClientError as exc:
                code = str(exc.response.get("Error", {}).get("Code", ""))
                if code in {"404", "NoSuchBucket", "NotFound"}:
                    self._client.create_bucket(Bucket=self.bucket)
                    log.info("artifacts.bucket_created", bucket=self.bucket)
                else:
                    raise

        await asyncio.to_thread(_ensure)

    async def put(self, run_id: str, name: str, data: bytes, content_type: str) -> StoredArtifact:
        key = artifact_key(run_id, name)
        digest = hashlib.sha256(data).hexdigest()

        def _put() -> None:
            self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                Metadata={"sha256": digest, "run-id": run_id},
            )

        await asyncio.to_thread(_put)
        return StoredArtifact(
            key=key, size_bytes=len(data), sha256=digest, content_type=content_type
        )

    async def get(self, run_id: str, name: str) -> bytes:
        key = artifact_key(run_id, name)

        def _get() -> bytes:
            response = self._client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()

        return await asyncio.to_thread(_get)

    async def exists(self, run_id: str, name: str) -> bool:
        key = artifact_key(run_id, name)

        def _head() -> bool:
            from botocore.exceptions import ClientError

            try:
                self._client.head_object(Bucket=self.bucket, Key=key)
                return True
            except ClientError:
                return False

        return await asyncio.to_thread(_head)

    async def list(self, run_id: str) -> list[str]:
        prefix = f"runs/{validate_run_id(run_id)}/"

        def _list() -> list[str]:
            response = self._client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
            return sorted(
                item["Key"][len(prefix) :] for item in response.get("Contents", []) if "Key" in item
            )

        return await asyncio.to_thread(_list)

    def describe(self) -> str:
        return f"s3:{self.endpoint_url}/{self.bucket}"


def create_artifact_store(settings: PlatformSettings) -> ArtifactStore:
    if settings.artifact_store == "local":
        return LocalArtifactStore(settings.artifact_local_dir)
    return S3ArtifactStore(
        endpoint_url=settings.s3_endpoint_url,
        region=settings.s3_region,
        bucket=settings.s3_bucket,
        access_key=settings.s3_access_key.get_secret_value(),
        secret_key=settings.s3_secret_key.get_secret_value(),
        force_path_style=settings.s3_force_path_style,
    )
