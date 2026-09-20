"""Collect non-sensitive provenance information about the running platform."""

from __future__ import annotations

import platform
import sys

from reslab_core.versions import SOFTWARE_VERSION
from reslab_platform.settings import PlatformSettings


def environment_metadata(settings: PlatformSettings) -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "platform": f"{platform.system()} {platform.machine()}",
        "software_version": SOFTWARE_VERSION,
        "environment": settings.environment,
    }


def image_versions(settings: PlatformSettings, *, component: str) -> dict[str, str]:
    versions: dict[str, str] = {}
    if settings.image_version:
        versions[component] = settings.image_version
    return versions


def python_executable() -> str:
    return sys.executable
