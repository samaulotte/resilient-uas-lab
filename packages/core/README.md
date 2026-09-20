# reslab-core

Pure domain library for Resilient UAS Lab. It has no I/O dependencies (no database, no
message bus, no HTTP) so that every other package can depend on it safely:

- `reslab_core.scenario`: versioned scenario schema, strict YAML loader, fault catalog
- `reslab_core.states`: component states, run lifecycle state machine, severities, event kinds
- `reslab_core.topology`: system domains, components, trust boundaries and dependency graph
- `reslab_core.telemetry`: normalized telemetry sample and run event models
- `reslab_core.adapter`: the generic `AutonomousSystemAdapter` contract
- `reslab_core.engine`: scenario engine that drives an adapter through a scenario
- `reslab_core.analysis`: assertions (declarative, no code execution), metrics, propagation, scoring
- `reslab_core.report`: canonical JSON report model and standalone HTML renderer
- `reslab_core.protocol`: runner protocol messages exchanged over the event bus

See `docs/architecture.md` at the repository root for how the pieces fit together.
