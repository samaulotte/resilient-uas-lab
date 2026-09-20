/**
 * Metric paths an assertion expression can reference.
 *
 * Mirrors the assertion context built by the analysis (`MetricsResult.assertion_context`).
 * Recovery paths per subsystem are derived from the topology: `recovery.<subsystem>` with
 * dots replaced by underscores, for example `recovery.mission_compute`.
 */

export type MetricPathKind = "bool" | "ratio" | "seconds" | "count";

export interface MetricPath {
  path: string;
  kind: MetricPathKind;
  description: string;
}

export const METRIC_PATH_GROUPS: readonly { group: string; paths: readonly MetricPath[] }[] = [
  {
    group: "Safety",
    paths: [
      {
        path: "flight_control.available",
        kind: "bool",
        description: "The flight core never left a healthy state",
      },
      {
        path: "flight_control.availability",
        kind: "ratio",
        description: "Fraction of the run with a healthy flight core",
      },
      {
        path: "control.availability",
        kind: "ratio",
        description: "Same value as flight_control.availability",
      },
      {
        path: "safety.loss_of_control",
        kind: "bool",
        description: "Control authority was lost at least once",
      },
      {
        path: "safety.preserved",
        kind: "bool",
        description: "No loss of control and the flight core stayed available",
      },
      {
        path: "safety.safe_state_reached",
        kind: "bool",
        description: "A safe-state response (failsafe hold, return to launch) was observed",
      },
    ],
  },
  {
    group: "Recovery",
    paths: [
      { path: "recovery.mttr", kind: "seconds", description: "Mean time to recovery" },
      { path: "recovery.max", kind: "seconds", description: "Slowest recovery" },
      { path: "recovery.success_rate", kind: "ratio", description: "Recovered over required" },
      { path: "recovery.count", kind: "count", description: "Number of faults recovered" },
      { path: "recovery.required", kind: "count", description: "Faults that had to recover" },
      {
        path: "recovery.time_to_safe_state",
        kind: "seconds",
        description: "Delay from the triggering fault to the first safe-state response",
      },
      {
        path: "recovery.<subsystem>",
        kind: "seconds",
        description:
          "Maximum recovery time of one subsystem, with dots replaced by underscores, for example recovery.mission_compute",
      },
    ],
  },
  {
    group: "Containment",
    paths: [
      {
        path: "containment.flight_domain_affected",
        kind: "bool",
        description: "A fault reached flight control or actuation",
      },
      {
        path: "containment.critical_domain_reached",
        kind: "bool",
        description: "Same as containment.flight_domain_affected",
      },
      { path: "containment.contained", kind: "bool", description: "No flight-critical domain hit" },
      {
        path: "containment.boundary_crossed",
        kind: "bool",
        description: "A dependency crossing a trust boundary had both ends affected",
      },
      {
        path: "containment.affected_domains",
        kind: "count",
        description: "Number of domains with at least one affected component",
      },
      {
        path: "containment.affected_components",
        kind: "count",
        description: "Components observed leaving a healthy state",
      },
      {
        path: "containment.propagated_components",
        kind: "count",
        description: "Affected components that were not injection targets",
      },
      {
        path: "containment.propagation_depth",
        kind: "count",
        description: "Longest dependency distance from an injection target",
      },
    ],
  },
  {
    group: "Mission",
    paths: [
      { path: "mission.completion", kind: "ratio", description: "Highest mission progress reached" },
      {
        path: "mission.continuity",
        kind: "ratio",
        description: "1 minus the fraction of the run spent holding or diverted",
      },
      { path: "mission.completed", kind: "bool", description: "Mission reached the COMPLETE phase" },
      { path: "mission.duration", kind: "seconds", description: "Simulation duration of the run" },
    ],
  },
  {
    group: "Availability",
    paths: [
      {
        path: "navigation.integrity",
        kind: "ratio",
        description: "Weighted navigation estimator availability",
      },
      {
        path: "navigation.availability",
        kind: "ratio",
        description: "Fraction of the run with a healthy navigation estimator",
      },
      {
        path: "communications.availability",
        kind: "ratio",
        description: "Fraction of the run with healthy communications",
      },
      {
        path: "compute.availability",
        kind: "ratio",
        description: "Fraction of the run with healthy mission compute",
      },
      {
        path: "power.availability",
        kind: "ratio",
        description: "Fraction of the run with healthy power",
      },
    ],
  },
  {
    group: "Time and events",
    paths: [
      { path: "time.nominal", kind: "seconds", description: "Time with every component healthy" },
      { path: "time.degraded", kind: "seconds", description: "Time in a degraded system mode" },
      { path: "time.failed", kind: "seconds", description: "Time in a failed system mode" },
      { path: "time.total", kind: "seconds", description: "Observed run duration" },
      { path: "events.injected", kind: "count", description: "Injection requests" },
      { path: "events.applied", kind: "count", description: "Injections confirmed by the adapter" },
      { path: "events.rejected", kind: "count", description: "Injections the adapter refused" },
      {
        path: "events.observed_effects",
        kind: "count",
        description: "Component state changes observed",
      },
      { path: "events.recoveries", kind: "count", description: "Recovery events" },
      {
        path: "events.expectations_failed",
        kind: "count",
        description: "Declared expectations that were not met",
      },
    ],
  },
];

export const ALL_METRIC_PATHS: readonly MetricPath[] = METRIC_PATH_GROUPS.flatMap(
  (group) => group.paths,
);

/** Suggested comparison for a metric path, used when inserting an assertion. */
export function suggestedExpression(path: MetricPath): string {
  switch (path.kind) {
    case "bool":
      return `${path.path} == true`;
    case "ratio":
      return `${path.path} >= 0.90`;
    case "seconds":
      return `${path.path} < 10s`;
    default:
      return `${path.path} <= 1`;
  }
}
