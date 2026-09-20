"use client";

import { ScenarioStudio } from "@/components/scenario/studio";
import { emptyDraft, type ScenarioDraft } from "@/lib/scenario-document";

/** A minimal but valid starting point: one disturbance and the three safety assertions. */
function starterDraft(): ScenarioDraft {
  const base = emptyDraft();
  return {
    ...base,
    name: "new-scenario",
    description: "Describe what this scenario validates.",
    tags: [],
    events: [
      {
        id: "gnss-loss",
        at: "30s",
        subsystem: "navigation.gnss",
        effect: "unavailable",
        duration: "40s",
        parameters: [],
        expect: [
          {
            subsystem: "navigation.estimator",
            state: "DEGRADED",
            within: "3s",
            description: "",
          },
        ],
        description: "GNSS aiding is lost while enroute",
      },
    ],
    assertions: [
      {
        expression: "flight_control.available == true",
        severity: "critical",
        description: "The flight core never leaves a healthy state",
      },
      { expression: "safety.loss_of_control == false", severity: "critical", description: "" },
      {
        expression: "containment.flight_domain_affected == false",
        severity: "critical",
        description: "No fault crosses the mission and flight trust boundary",
      },
    ],
  };
}

export function NewScenarioView() {
  return <ScenarioStudio initialDraft={starterDraft()} />;
}
