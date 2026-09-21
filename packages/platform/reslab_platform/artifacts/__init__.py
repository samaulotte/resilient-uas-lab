"""Artifact storage abstraction (S3-compatible object store or local directory)."""

from reslab_platform.artifacts.store import (
    ArtifactStore,
    LocalArtifactStore,
    S3ArtifactStore,
    StoredArtifact,
    artifact_key,
    create_artifact_store,
)

__all__ = [
    "ArtifactStore",
    "LocalArtifactStore",
    "S3ArtifactStore",
    "StoredArtifact",
    "artifact_key",
    "create_artifact_store",
]
