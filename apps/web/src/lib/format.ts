/**
 * Formatting helpers for comparison tables and metric readouts.
 *
 * A "changed" verdict is deliberately neutral: the platform cannot decide whether a
 * neutral metric moved in a good or a bad direction, and the UI must not pretend it can.
 */

import type { MetricComparison } from "@reslab/api-client";

import type { Tone } from "@/lib/states";

export type MetricUnit = MetricComparison["unit"];
export type ComparisonVerdict = MetricComparison["verdict"];
export type BetterDirection = MetricComparison["better"];

export const VERDICT_LABEL: Record<ComparisonVerdict, string> = {
  improvement: "IMPROVEMENT",
  regression: "REGRESSION",
  unchanged: "UNCHANGED",
  changed: "CHANGED",
  not_comparable: "NOT COMPARABLE",
};

export const VERDICT_TONE: Record<ComparisonVerdict, Tone> = {
  improvement: "ok",
  regression: "bad",
  unchanged: "dim",
  changed: "info",
  not_comparable: "dim",
};

export function verdictTone(verdict: ComparisonVerdict): Tone {
  return VERDICT_TONE[verdict];
}

/** Render a comparison value according to its declared unit. */
export function formatMetricValue(value: number | boolean | null, unit: MetricUnit): string {
  if (value === null || value === undefined) return "n/a";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (Number.isNaN(value)) return "n/a";
  switch (unit) {
    case "percent":
      return `${(value * 100).toFixed(1)}%`;
    case "seconds":
      return `${value.toFixed(value < 10 ? 2 : 1)}s`;
    case "count":
      return Number.isInteger(value) ? String(value) : value.toFixed(1);
    case "score":
      return value.toFixed(1);
    case "bool":
      return value ? "true" : "false";
    default:
      return String(value);
  }
}

/** Render a signed delta; percent deltas are expressed in percentage points. */
export function formatMetricDelta(delta: number | null, unit: MetricUnit): string {
  if (delta === null || delta === undefined || Number.isNaN(delta)) return "n/a";
  if (unit === "bool") return delta === 0 ? "same" : "changed";
  const sign = delta > 0 ? "+" : delta < 0 ? "-" : "";
  const magnitude = Math.abs(delta);
  switch (unit) {
    case "percent":
      return `${sign}${(magnitude * 100).toFixed(1)} pp`;
    case "seconds":
      return `${sign}${magnitude.toFixed(magnitude < 10 ? 2 : 1)}s`;
    case "count":
      return `${sign}${Number.isInteger(magnitude) ? magnitude : magnitude.toFixed(1)}`;
    case "score":
      return `${sign}${magnitude.toFixed(1)}`;
    default:
      return `${sign}${magnitude}`;
  }
}

export const BETTER_LABEL: Record<BetterDirection, string> = {
  higher: "higher is better",
  lower: "lower is better",
  neutral: "no preferred direction",
};

/** Format a score on the 0-100 scale, or a dash when the run was not analyzed. */
export function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined || Number.isNaN(score)) return "--";
  return score.toFixed(1);
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Format a heading in degrees from a yaw angle in radians (0 = north, clockwise). */
export function formatHeading(yaw: number | null | undefined): string {
  if (yaw === null || yaw === undefined || Number.isNaN(yaw)) return "n/a";
  const degrees = ((yaw * 180) / Math.PI + 360) % 360;
  return `${degrees.toFixed(0).padStart(3, "0")}deg`;
}

export function formatMetres(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${value.toFixed(digits)} m`;
}

export function formatSpeed(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${value.toFixed(1)} m/s`;
}
