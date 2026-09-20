# Scoring

The resilience score is a transparent, configurable summary of the metrics of a run. It
is a number on a 0 to 100 scale computed from documented dimensions with integer
weights, and it is subordinate to three hard gates that decide the benchmark result
regardless of the number. The implementation is `compute_score` in
`packages/core/reslab_core/analysis/scoring.py`; the inputs are the metrics defined in
[metrics](metrics.md) and the assertion results.

The score exists to compare runs and to track regressions. It does not certify
anything: a run scoring 95 with a failed critical assertion is `failed`.

## Result before score

Every run has a `result` of `passed`, `failed` or `inconclusive`, decided by hard
gates evaluated in this order:

| Gate | Passes when | Reason text on failure |
| ---- | ----------- | ---------------------- |
| `critical_assertions` | No assertion with severity `critical` has outcome `failed` | `critical assertion violated: <expressions>` |
| `control_authority` | `safety.loss_of_control` is false | `loss of control observed` |
| `run_completed` | The run reached `COMPLETED` (or is being analyzed on the way there) | `run did not complete` |

- If `run_completed` fails, the result is `inconclusive` with the reason
  `run did not complete; result is inconclusive`. This is what cancelled and failed
  runs receive when the orchestrator produces their best-effort report.
- Otherwise, if every gate passes, the result is `passed` with reason
  `all hard gates passed`.
- Otherwise the result is `failed` and the reason lists the failed gates.

`report.json` carries both `result` and `hard_gate_result`; in this release they are
always equal. The run's `reason` field is set to the score reason when the run
completes. A `critical` assertion that is `not_evaluated` (its metric was not available)
does not fail the gate; only `failed` does.

## Dimensions

Each dimension is a value in `[0, 1]` derived from metrics, multiplied by its weight to
give points. The total is the sum of points, rounded to one decimal and clamped to
`[0, 100]`.

| Dimension | Label | Score in `[0, 1]` | Explanation text |
| --------- | ----- | ----------------- | ---------------- |
| `safety` | Safety preservation | `0` if `safety.loss_of_control`, else `availability.control` | `loss of control` or `flight control available N% of the run` |
| `mission_continuity` | Mission continuity | `0.5 * mission.completion + 0.5 * mission.continuity` | `completion N%, continuity N%` |
| `recovery` | Recovery capability | See below | `k/n recovered, MTTR Ns (target 5s, limit 30s)` |
| `containment` | Fault containment | `0` if `critical_domain_reached`, else `1 - penalty * len(propagated_domains)` | `fault reached the flight-critical domain` or `propagated to N domain(s): ...` |
| `navigation` | Navigation integrity | `availability.navigation_integrity` | `navigation integrity N%` |
| `communications` | Communications | `availability.communications` | `communications available N%` |
| `compute` | Compute availability | `availability.compute` | `mission compute available N%` |

### Recovery dimension

Given the recovery metrics and the profile parameters `mttr_target` (default 5 s) and
`mttr_limit` (default 30 s):

1. If no fault required recovery, the score is `1.0` (`no fault required recovery`).
2. If faults required recovery but none recovered (`recovery.mttr` is null), the score
   is `0.0`.
3. Otherwise `speed` is `1.0` when MTTR is at or below the target, `0.0` when at or
   above the limit, and linear in between:
   `1 - (mttr - target) / (limit - target)`. The score is
   `success_rate * speed`, clamped to `[0, 1]`.

A mission computer that restarts in 4.9 s scores `1.0`; one that takes 17.5 s scores
`0.5`; one that takes 30 s or more scores `0.0` even if it did come back.

### Containment dimension

With the default `containment_penalty_per_domain` of `0.25`, a fault that propagated
into one non-critical domain other than the injected ones scores `0.75`, into two
`0.5`, and so on. A fault confined to the domains it was injected into scores `1.0`
even if it spread to several components within them. Any propagation into
`flight_control` or `actuation` scores `0.0`. The definitions of injected, affected and
propagated domains are in [metrics](metrics.md).

## The default profile

```python
DEFAULT_SCORE_PROFILE = ScoreProfile(
    name="default",
    description=(
        "Balanced profile for autonomous flight: safety first, then mission continuity "
        "and recovery, then containment and navigation, then communications."
    ),
    weights={
        "safety": 30,
        "mission_continuity": 20,
        "recovery": 20,
        "containment": 15,
        "navigation": 10,
        "communications": 5,
        "compute": 0,
    },
)
```

Compute availability carries a weight of 0 in the default profile: its value is still
computed and shown, but it contributes no points. A companion computer outage still
affects the total through mission continuity (time in hold) and recovery. Profiles that
care about companion compute uptime can give the dimension weight. The comparison view
hides dimensions whose weight is 0.

Parameters, all part of the profile:

| Parameter | Default | Constraint |
| --------- | ------- | ---------- |
| `mttr_target` | `5.0` s | greater than 0 |
| `mttr_limit` | `30.0` s | greater than `mttr_target` |
| `containment_penalty_per_domain` | `0.25` | between 0 and 1 |

## A worked example

The `gnss-loss` starter scenario on the mock adapter produced this breakdown in this
release (the values are deterministic for seed 7):

| Dimension | Weight | Score | Points | Explanation |
| --------- | ------ | ----- | ------ | ----------- |
| safety | 30 | 1.0 | 30.0 | flight control available 100.0% of the run |
| mission_continuity | 20 | 1.0 | 20.0 | completion 100.0%, continuity 100.0% |
| recovery | 20 | 1.0 | 20.0 | 2/2 recovered, MTTR 0.1s (target 5s, limit 30s) |
| containment | 15 | 1.0 | 15.0 | propagated to 0 domain(s): none |
| navigation | 10 | 0.8516 | 8.52 | navigation integrity 85.2% |
| communications | 5 | 1.0 | 5.0 | communications available 100.0% |
| compute | 0 | 1.0 | 0.0 | mission compute available 100.0% |

Total 98.5, all three gates passed, result `passed`. The only lost points come from the
40 s the estimator spent in dead reckoning (weighted 0.5 in navigation integrity). The
same table appears in `report.html` under "Score breakdown" and in the run detail
Metrics tab.

## Custom profiles

A `ScoreProfile` is validated as follows: the name matches
`^[a-z0-9][a-z0-9-]{0,62}$`, every weight names a known dimension, weights are
non-negative integers and sum to exactly 100, and the parameters satisfy the
constraints above. Unknown keys are rejected.

Profiles can be loaded from YAML with `load_score_profile`, which accepts either a bare
mapping or a mapping under a `score_profile` key:

```yaml
score_profile:
  name: recovery-focused
  description: Weighs recovery and containment more than mission progress.
  weights:
    safety: 30
    mission_continuity: 10
    recovery: 30
    containment: 20
    navigation: 5
    communications: 5
    compute: 0
  parameters:
    mttr_target: 3.0
    mttr_limit: 20.0
    containment_penalty_per_domain: 0.5
```

How a profile is selected at run time:

- A scenario names its profile in `scoring.profile` (default `default`).
- The orchestrator looks the name up in the `score_profiles` table
  (`repository.get_score_profile`). If it is missing the analysis logs
  `analysis.profile_missing` and uses the default profile. The name actually used is
  recorded in the report's provenance (`score_profile`).
- The `migrate` service seeds only the `default` profile
  (`reslab_platform/seed.py`). There is no API endpoint or CLI command to create
  profiles in this release; a custom profile has to be inserted with
  `repository.upsert_score_profile` (for example from a small script using the
  platform package) before runs reference it. `GET /api/v1/system` lists the profiles
  known to the platform under `score_profiles`, and the System page shows them.
- `reslab run --local` and `run_locally` accept a `ScoreProfile` object
  programmatically but the CLI exposes no flag for it; local runs use the default
  profile.

Changing a profile changes scores, not results: hard gates do not depend on weights.
Runs scored with different profiles should not be compared by their totals, which is
why the report records the profile name.

## Where the score appears

| Place | Fields |
| ----- | ------ |
| `report.json` | `result`, `resilience_score`, `hard_gate_result`, `score` (profile, total, dimensions with points and explanations, hard gates with reasons) |
| `runs` table and `RunSummary` | `result`, `hard_gate_result`, `resilience_score`, `summary` |
| `GET /api/v1/runs/{id}/metrics` | `score` alongside `metrics`, `context` and `assertions` |
| Mission Control and run detail | The score KPI, the score breakdown component, badges for the result |
| `reslab run`, `reslab report` | `Result PASSED (score 98.5 / 100)` in the summary |
| `GET /api/v1/compare` | `score.total` as the first compared metric, dimensions compared by points with a 0.05 point tolerance |
| `reslab regression check` | `require_passed` (the result must be `passed`) and `score_drop_max` (default 5.0 points) |

## Summary figures

Besides the score, `report.json` carries a `summary` generated from observed events:
`mission_complete`, `faults_injected`, `faults_applied`, `critical_failures` (observed
effects of severity `critical`), `recovered_subsystems`, `degraded_transitions`,
`loss_of_control`, `safety_preservation` (`PASS` or `FAIL` from `safety.preserved`),
`fault_containment` (`PASS` or `FAIL` from `propagation.contained`),
`mean_time_to_recovery` and `affected_domains`. These are the figures shown as KPIs; none
of them is hard-coded or derived from the scenario's intent.
