"""Version constants shared by every component.

Each externally visible contract carries its own version so that it can evolve
independently and be migrated in a backward compatible way:

- `SCENARIO_API_VERSION`: the `apiVersion` accepted in scenario YAML files.
- `REPORT_SCHEMA_VERSION`: the `schema_version` written into `report.json`.
- `PROTOCOL_VERSION`: the runner protocol spoken over the event bus.
- `SOFTWARE_VERSION`: the platform release, recorded in run provenance.
"""

SOFTWARE_VERSION = "0.1.0"

SCENARIO_API_VERSION = "resilient-uas.dev/v1alpha1"
SCENARIO_KIND = "ResilienceScenario"
SUPPORTED_SCENARIO_API_VERSIONS: frozenset[str] = frozenset({SCENARIO_API_VERSION})

REPORT_SCHEMA_VERSION = "1.0"

PROTOCOL_VERSION = "1"
