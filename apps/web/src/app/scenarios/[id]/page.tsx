import type { Metadata } from "next";

import { ScenarioEditView } from "@/app/scenarios/[id]/scenario-edit-view";

export const metadata: Metadata = { title: "Scenario" };

export default async function ScenarioPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ScenarioEditView name={id} />;
}
