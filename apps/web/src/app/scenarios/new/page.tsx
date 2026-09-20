import type { Metadata } from "next";

import { NewScenarioView } from "@/app/scenarios/new/new-scenario-view";

export const metadata: Metadata = { title: "New scenario" };

export default function NewScenarioPage() {
  return <NewScenarioView />;
}
