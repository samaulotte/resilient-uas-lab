import type { Metadata } from "next";

import { ScenariosView } from "@/app/scenarios/scenarios-view";

export const metadata: Metadata = { title: "Scenarios" };

export default function ScenariosPage() {
  return <ScenariosView />;
}
