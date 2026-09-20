# Documentation

Resilient UAS Lab is a platform for measuring how an autonomous system behaves when
parts of it degrade. Scenarios are declarative YAML documents; runs execute them
against a target through an adapter; the result is a set of objective metrics, a
transparent score and a canonical report. The platform simulates the effects of
degradation only; it never models how a disturbance is produced.

Software version 0.1.0, scenario schema `resilient-uas.dev/v1alpha1`, report schema
`1.0`, runner protocol `1`.

## Start here

| Document | One line |
| -------- | -------- |
| [Getting started](getting-started.md) | From a clone to a completed run with a report: the in-process mock, then the full Compose stack, the UI tour, the CLI and the API |
| [Architecture](architecture.md) | Components, data flow of a run, run state machine, event bus subjects, persistence, analysis pipeline |

## Writing and reading scenarios

| Document | One line |
| -------- | -------- |
| [Scenario format](scenario-format.md) | The `v1alpha1` schema field by field, the fault catalog (17 subsystems, 11 effects), expectations, assertions, consequence profiles, validation rules and the starter library |
| [Resilience model](resilience-model.md) | The shared vocabulary: component states, system modes, event kinds, disturbance window and recovery, containment, safety |
| [Degraded modes](degraded-modes.md) | How the platform represents degraded operation, what the recovery policy means, and the degraded modes the mock adapter realizes |
| [Electromagnetic resilience](em-resilience.md) | The abstract consequence profile: what is modelled, what is excluded, and how the starter scenario expands |

## Understanding results

| Document | One line |
| -------- | -------- |
| [Metrics](metrics.md) | Every metric's definition, the recovery record semantics, propagation depth, the complete assertion context |
| [Scoring](scoring.md) | Dimensions, weights, formulas, hard gates, the default profile and custom profiles |
| [Safety model](safety-model.md) | What safety means here (control authority, flight core availability, safe states), how it is observed and how it decides the result |

## Security

| Document | One line |
| -------- | -------- |
| [Trust boundaries](trust-boundaries.md) | The zones and boundaries inside the modelled vehicle, how containment uses them, and a map of the platform's own boundaries |
| [Security model](security-model.md) | Controls as implemented: scenario loading, identifiers, API, bus, storage, containers, provenance, CI, and known limitations |
| [Threat model](threat-model.md) | The scope line of the tool, then assets, actors, threats, controls and residual risks of the platform |

## Running and extending

| Document | One line |
| -------- | -------- |
| [Deployment](deployment.md) | The Compose stack service by service, networks, volumes, every environment variable, profiles, hardening before sharing, upgrades |
| [PX4 integration](px4-integration.md) | The experimental PX4 SITL adapter: profile, transport, effect mapping, state derivation, limitations, and its unverified status in this release |
| [Adapter development](adapter-development.md) | The adapter contract, how the engine drives it, registration, testing and expectations |
| [Development](development.md) | Toolchain, running services locally, unit, integration and end-to-end tests, regression check, code generation, conventions, CI |
| [Roadmap](roadmap.md) | What is implemented and verified in 0.1.0, what is planned without code yet, and what is not planned |

## Elsewhere in the repository

- `CONTRIBUTING.md`: process, conventions, scenario and adapter contributions,
  versioning and releases.
- `SECURITY.md`: how to report a vulnerability, supported versions, scope.
- `CHANGELOG.md`: notable changes, with separate subsections for the scenario and report
  schemas.
- `adapters/px4-gazebo/README.md`, `packages/core/README.md`,
  `packages/client/README.md`: package-level notes.
- `packages/schemas/`: the published JSON Schemas and the OpenAPI document.
- `scenarios/`: the seven starter scenarios.
