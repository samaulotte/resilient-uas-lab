"""Export versioned JSON Schemas and the OpenAPI document into packages/schemas/.

Usage: uv run python scripts/export_schemas.py [--check]

`--check` exits non-zero when the committed files differ from the generated ones,
which CI uses to prevent drift between models and published schemas.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from reslab_core.report.model import ResilienceReport
from reslab_core.scenario.model import ResilienceScenario
from reslab_core.telemetry import RunEvent, TelemetrySample
from reslab_core.versions import REPORT_SCHEMA_VERSION, SCENARIO_API_VERSION

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "packages" / "schemas"


def _dump(data: dict) -> str:
    return json.dumps(data, indent=2, sort_keys=False) + "\n"


def generate() -> dict[str, str]:
    scenario_version = SCENARIO_API_VERSION.rsplit("/", 1)[1]
    files: dict[str, str] = {
        f"scenario.{scenario_version}.schema.json": _dump(
            ResilienceScenario.model_json_schema(by_alias=True)
        ),
        f"report.v{REPORT_SCHEMA_VERSION}.schema.json": _dump(ResilienceReport.model_json_schema()),
        "telemetry-sample.schema.json": _dump(TelemetrySample.model_json_schema()),
        "run-event.schema.json": _dump(RunEvent.model_json_schema()),
    }
    from reslab_api.app import create_app

    app = create_app()
    files["openapi.json"] = _dump(app.openapi())
    return files


def main(argv: list[str]) -> int:
    check = "--check" in argv
    files = generate()
    OUT.mkdir(parents=True, exist_ok=True)
    drift = []
    for name, content in files.items():
        path = OUT / name
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                drift.append(name)
        else:
            path.write_text(content, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")
    if check and drift:
        print("schema drift detected in: " + ", ".join(drift), file=sys.stderr)
        print("run `make schemas` and commit the result", file=sys.stderr)
        return 1
    if check:
        print("schemas are up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
