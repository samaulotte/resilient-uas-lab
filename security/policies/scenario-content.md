# Scenario content policy

Scenario documents are the only user-authored input the platform executes, so their
contract is deliberately narrow. This policy states the contract; the loader and the
schema in `packages/core/reslab_core/scenario/` enforce it, and the tests in
`packages/core/tests/test_scenario_loader.py` pin the enforcement.

## Declarative only

1. A scenario is data. It is parsed by a restricted YAML loader (`yaml.SafeLoader` with
   stricter mapping rules) that constructs only plain scalars, sequences and mappings
   with string keys. Custom tags and Python object constructors are rejected; anchors
   and aliases can only repeat plain data.
2. A scenario never causes code to be executed, a shell to be invoked, a module to be
   imported, or a file outside the scenario library to be read. Neither the schema nor
   the engine has a field or a code path for any of these, and none will be added.
3. Documents are limited in size (256 KiB), must contain exactly one YAML document, and
   duplicate keys are an error rather than a silent override.
4. Every key is known. Unknown keys anywhere in the document are validation errors;
   there is no free-form `extra` or `params` bag that passes through to an adapter.
5. Effects and their parameters come from a closed catalogue. An effect not in the
   catalogue, a parameter not whitelisted for that effect, or a value outside its
   declared range is rejected before a run is created.
6. Identifiers are constrained: subsystem ids, event ids and scenario names match
   fixed patterns, so they can be used safely in file names, storage keys, event
   subjects and HTML without escaping surprises.

## Effects only

7. A scenario describes what a subsystem experiences (unavailable, degraded, restart,
   intermittent, latency, and so on), never how that experience is brought about. There
   is no field for a source, an emitter, a signal, a power level, a frequency, an antenna,
   a distance, or any physical parameter of a disturbance. Consequence profiles are a
   map from subsystem to abstract effect with a start time and a duration.
8. Contributions that would add such fields, or scenarios whose descriptions explain
   how to cause the modelled effects on a real system, are declined. See
   `docs/threat-model.md` for the scope line and its rationale.

## Provenance

9. The canonical content hash of a scenario (`sha256:` over the normalised JSON form)
   is recorded with every run and printed in every report, so a result can always be
   tied to the exact document that produced it.
10. Scenarios in the library are seeded from the repository at start-up. Documents
    submitted through the API are validated by the same code path and stored with the
    same hash; the platform never rewrites a submitted document.

## Review checklist

- Does `reslab scenario validate <file>` accept the document without warnings?
- Do all expectations and assertions refer to observable behaviour in the shared
  vocabulary (`docs/resilience-model.md`)?
- Does the description talk about consequences and expected behaviour only?
- Does the scenario pass on the mock adapter, and is its pass deterministic for a
  given seed?
