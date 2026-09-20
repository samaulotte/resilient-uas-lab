import { describe, expect, it } from "vitest";

import { parseDuration, toDurationString } from "@/lib/duration";
import {
  formatMetricDelta,
  formatMetricValue,
  formatScore,
  verdictTone,
} from "@/lib/format";
import { formatDuration, formatMissionTime, formatPercent } from "@/lib/utils";

describe("formatMissionTime", () => {
  it("formats simulation seconds as T+MM:SS", () => {
    expect(formatMissionTime(0)).toBe("T+00:00");
    expect(formatMissionTime(65.4)).toBe("T+01:05");
    expect(formatMissionTime(3599)).toBe("T+59:59");
  });

  it("keeps the sign for negative times and degrades gracefully", () => {
    expect(formatMissionTime(-5)).toBe("T-00:05");
    expect(formatMissionTime(null)).toBe("T+--:--");
    expect(formatMissionTime(Number.NaN)).toBe("T+--:--");
  });
});

describe("formatDuration", () => {
  it("switches unit with magnitude", () => {
    expect(formatDuration(0.25)).toBe("250ms");
    expect(formatDuration(4.2)).toBe("4.2s");
    expect(formatDuration(9)).toBe("9s");
    expect(formatDuration(65)).toBe("1m05s");
  });

  it("reports missing values instead of guessing", () => {
    expect(formatDuration(null)).toBe("n/a");
  });
});

describe("formatPercent", () => {
  it("scales a ratio", () => {
    expect(formatPercent(0.9661)).toBe("96.6%");
    expect(formatPercent(1, 0)).toBe("100%");
    expect(formatPercent(undefined)).toBe("n/a");
  });
});

describe("duration strings", () => {
  it("parses the forms accepted by the scenario schema", () => {
    expect(parseDuration("30s")).toBe(30);
    expect(parseDuration("1m30s")).toBe(90);
    expect(parseDuration("250ms")).toBe(0.25);
    expect(parseDuration("1h2m3s")).toBe(3723);
  });

  it("rejects a bare number and nonsense", () => {
    expect(parseDuration("30")).toBeNull();
    expect(parseDuration("")).toBeNull();
    expect(parseDuration("soon")).toBeNull();
  });

  it("round trips through the canonical form", () => {
    expect(toDurationString(30)).toBe("30s");
    expect(toDurationString(90)).toBe("1m30s");
    expect(toDurationString(120)).toBe("2m");
    expect(parseDuration(toDurationString(45.5))).toBe(45.5);
  });
});

describe("comparison formatting", () => {
  it("formats values by unit", () => {
    expect(formatMetricValue(0.9661, "percent")).toBe("96.6%");
    expect(formatMetricValue(4.9, "seconds")).toBe("4.90s");
    expect(formatMetricValue(3, "count")).toBe("3");
    expect(formatMetricValue(92.2, "score")).toBe("92.2");
    expect(formatMetricValue(true, "bool")).toBe("true");
    expect(formatMetricValue(null, "percent")).toBe("n/a");
  });

  it("expresses percent deltas in percentage points", () => {
    expect(formatMetricDelta(0.3963, "percent")).toBe("+39.6 pp");
    expect(formatMetricDelta(-0.05, "percent")).toBe("-5.0 pp");
    expect(formatMetricDelta(7.5, "score")).toBe("+7.5");
    expect(formatMetricDelta(null, "count")).toBe("n/a");
  });

  it("never colours a neutral change as better or worse", () => {
    expect(verdictTone("improvement")).toBe("ok");
    expect(verdictTone("regression")).toBe("bad");
    expect(verdictTone("changed")).toBe("info");
    expect(verdictTone("unchanged")).toBe("dim");
    expect(verdictTone("not_comparable")).toBe("dim");
  });

  it("marks a missing score instead of showing zero", () => {
    expect(formatScore(null)).toBe("--");
    expect(formatScore(92.2)).toBe("92.2");
  });
});
