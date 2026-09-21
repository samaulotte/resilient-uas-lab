"""Every distribution in the repository declares the same version.

The release version is stated in seventeen places: `SOFTWARE_VERSION`, ten Python
distributions, three Node packages and the three adapter constants that are written
into run provenance. A release that bumps some of them and not others produces a build
that misreports itself in `report.json`, which is exactly the kind of unverifiable
claim this project refuses to make. The test fails rather than letting them drift.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

from reslab_core.versions import SOFTWARE_VERSION

REPO_ROOT = Path(__file__).resolve().parents[3]

PYTHON_DISTRIBUTIONS = (
    "pyproject.toml",
    "packages/core/pyproject.toml",
    "packages/platform/pyproject.toml",
    "packages/cli/pyproject.toml",
    "services/api/pyproject.toml",
    "services/orchestrator/pyproject.toml",
    "services/runner/pyproject.toml",
    "adapters/mock/pyproject.toml",
    "adapters/px4-gazebo/pyproject.toml",
    "adapters/replay/pyproject.toml",
)

NODE_PACKAGES = (
    "package.json",
    "packages/client/package.json",
    "apps/web/package.json",
)

ADAPTER_CONSTANTS = (
    ("adapters/mock/reslab_adapter_mock/adapter.py", "MOCK_ADAPTER_VERSION"),
    ("adapters/px4-gazebo/reslab_adapter_px4/adapter.py", "PX4_ADAPTER_VERSION"),
    ("adapters/replay/reslab_adapter_replay/adapter.py", "REPLAY_ADAPTER_VERSION"),
)

pytestmark = pytest.mark.skipif(
    not (REPO_ROOT / "pyproject.toml").is_file(),
    reason="the version set is checked against the source tree, not an installed wheel",
)


@pytest.mark.parametrize("relative_path", PYTHON_DISTRIBUTIONS)
def test_python_distribution_matches_software_version(relative_path: str) -> None:
    manifest = tomllib.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))
    assert manifest["project"]["version"] == SOFTWARE_VERSION


@pytest.mark.parametrize("relative_path", NODE_PACKAGES)
def test_node_package_matches_software_version(relative_path: str) -> None:
    manifest = json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))
    assert manifest["version"] == SOFTWARE_VERSION


@pytest.mark.parametrize(("relative_path", "constant"), ADAPTER_CONSTANTS)
def test_adapter_constant_matches_software_version(relative_path: str, constant: str) -> None:
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    match = re.search(rf'^{constant} = "(?P<version>[^"]+)"$', source, re.MULTILINE)
    assert match is not None, f"{constant} is not declared in {relative_path}"
    assert match.group("version") == SOFTWARE_VERSION


def test_changelog_documents_the_current_version() -> None:
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"\n## [{SOFTWARE_VERSION}]" in changelog
