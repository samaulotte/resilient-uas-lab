import { load } from "js-yaml";
import { describe, expect, it } from "vitest";

import {
  draftToYaml,
  emptyDraft,
  parseScenarioDocument,
  ScenarioParseError,
  scenarioSchedule,
  type ScenarioDraft,
} from "@/lib/scenario-document";

const COMPOUND = `apiVersion: resilient-uas.dev/v1alpha1
kind: ResilienceScenario

metadata:
  name: compound-degradation
  description: Sequential navigation, communications and compute degradation.
  version: "1"
  tags: [demo, containment]

target:
  adapter: mock
  vehicle: x500

mission:
  type: waypoint
  timeout: 180s
  altitude: 30
  cruise_speed: 6.0

recovery:
  gnss_loss: dead_reckoning
  datalink_loss: continue
  compute_loss: hold
  hold_timeout: 60s
  max_dead_reckoning: 120s

simulation:
  seed: 42
  speed: 1.0

events:
  - id: gnss-loss
    at: 30s
    description: GNSS receiver stops delivering fixes
    inject:
      subsystem: navigation.gnss
      effect: unavailable
    expect:
      - subsystem: navigation.estimator
        state: DEGRADED
        within: 3s
      - subsystem: flight_control.core
        state: OPERATIONAL
        within: 1s

  - id: c2-loss
    at: 45s
    inject:
      subsystem: communications.c2
      effect: temporary_disconnect
      duration: 20s

  - id: mission-compute-restart
    at: 60s
    inject:
      subsystem: mission.compute
      effect: restart

assertions:
  - expression: flight_control.available == true
    severity: critical
    description: The flight core never leaves an operational state
  - expression: mission.completion >= 0.80
    severity: medium
`;

function yamlObject(text: string): Record<string, unknown> {
  const parsed = load(text);
  if (typeof parsed !== "object" || parsed === null) throw new Error("not a mapping");
  return parsed as Record<string, unknown>;
}

describe("parseScenarioDocument", () => {
  it("reads a compound scenario into the studio form", () => {
    const draft = parseScenarioDocument(COMPOUND);
    expect(draft.name).toBe("compound-degradation");
    expect(draft.tags).toEqual(["demo", "containment"]);
    expect(draft.adapter).toBe("mock");
    expect(draft.timeout).toBe("180s");
    expect(draft.altitude).toBe(30);
    expect(draft.cruiseSpeed).toBe(6);
    expect(draft.recovery.maxDeadReckoning).toBe("120s");
    expect(draft.seed).toBe(42);
    expect(draft.events).toHaveLength(3);
    expect(draft.events[0]?.subsystem).toBe("navigation.gnss");
    expect(draft.events[0]?.expect).toHaveLength(2);
    expect(draft.events[1]?.duration).toBe("20s");
    expect(draft.events[2]?.duration).toBe("");
    expect(draft.assertions[0]?.severity).toBe("critical");
  });

  it("rejects malformed YAML instead of crashing", () => {
    expect(() => parseScenarioDocument("a:\n  - b\n - c")).toThrow(ScenarioParseError);
    expect(() => parseScenarioDocument("just a string")).toThrow(ScenarioParseError);
  });
});

describe("draftToYaml", () => {
  it("emits the schema key order", () => {
    const yaml = draftToYaml(parseScenarioDocument(COMPOUND));
    expect(Object.keys(yamlObject(yaml))).toEqual([
      "apiVersion",
      "kind",
      "metadata",
      "target",
      "mission",
      "recovery",
      "simulation",
      "events",
      "assertions",
    ]);
  });

  it("round trips a compound scenario without losing anything the form edits", () => {
    const first = parseScenarioDocument(COMPOUND);
    const second = parseScenarioDocument(draftToYaml(first));
    expect(second).toEqual(first);
    expect(draftToYaml(second)).toBe(draftToYaml(first));
  });

  it("omits an empty duration rather than writing null", () => {
    const yaml = draftToYaml(parseScenarioDocument(COMPOUND));
    const document = yamlObject(yaml);
    const events = document.events as { id: string; inject: Record<string, unknown> }[];
    expect(events[0]?.inject).not.toHaveProperty("duration");
    expect(events[1]?.inject.duration).toBe("20s");
  });

  it("writes effect parameters as numbers and durations", () => {
    const draft: ScenarioDraft = {
      ...emptyDraft(),
      name: "parametrised",
      events: [
        {
          id: "intermittent-gnss",
          at: "20s",
          subsystem: "navigation.gnss",
          effect: "intermittent",
          duration: "30s",
          parameters: [
            { name: "period", value: "2s", kind: "duration" },
            { name: "duty_cycle", value: "0.4", kind: "ratio" },
            { name: "ignored", value: "", kind: "number" },
          ],
          expect: [],
          description: "",
        },
      ],
      assertions: [],
    };
    const document = yamlObject(draftToYaml(draft));
    const events = document.events as { inject: { parameters: Record<string, unknown> } }[];
    expect(events[0]?.inject.parameters).toEqual({ period: "2s", duty_cycle: 0.4 });
  });

  it("preserves a consequence profile the form does not edit", () => {
    const withProfile = `apiVersion: resilient-uas.dev/v1alpha1
kind: ResilienceScenario
metadata:
  name: em-transient-profile-a
target:
  adapter: mock
mission:
  timeout: 180s
profile:
  name: em-transient-profile-a
  at: 40s
  duration: 8s
  effects:
    navigation.gnss: intermittent
    mission.compute: restart
    flight_control.core: operational
assertions:
  - expression: safety.loss_of_control == false
    severity: critical
`;
    const draft = parseScenarioDocument(withProfile);
    const document = yamlObject(draftToYaml(draft));
    expect(document.profile).toMatchObject({ name: "em-transient-profile-a", at: "40s" });
  });
});

describe("scenarioSchedule", () => {
  it("orders explicit events by time", () => {
    const schedule = scenarioSchedule(parseScenarioDocument(COMPOUND));
    expect(schedule.map((entry) => entry.id)).toEqual([
      "gnss-loss",
      "c2-loss",
      "mission-compute-restart",
    ]);
    expect(schedule[0]?.at).toBe(30);
    expect(schedule[1]?.duration).toBe("20s");
  });

  it("expands a consequence profile the way the engine does", () => {
    const draft: ScenarioDraft = {
      ...emptyDraft(),
      name: "em",
      preserved: {
        profile: {
          name: "em-transient-profile-a",
          at: "40s",
          duration: "8s",
          effects: {
            "navigation.gnss": "intermittent",
            "mission.compute": "restart",
            "flight_control.core": "operational",
          },
        },
      },
    };
    const schedule = scenarioSchedule(draft);
    expect(schedule).toHaveLength(2);
    expect(schedule.every((entry) => entry.fromProfile)).toBe(true);
    expect(schedule.map((entry) => entry.id)).toEqual([
      "em-transient-profile-a-mission-compute",
      "em-transient-profile-a-navigation-gnss",
    ]);
    // A transient effect never carries the profile duration.
    const restart = schedule.find((entry) => entry.effect === "restart");
    expect(restart?.duration).toBeNull();
    const intermittent = schedule.find((entry) => entry.effect === "intermittent");
    expect(intermittent?.duration).toBe("8s");
  });
});
