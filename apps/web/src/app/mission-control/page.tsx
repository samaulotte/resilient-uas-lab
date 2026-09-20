import type { Metadata } from "next";
import { Suspense } from "react";

import { MissionControlView } from "@/app/mission-control/mission-control-view";
import { LoadingPanel } from "@/components/ui/feedback";

export const metadata: Metadata = { title: "Mission Control" };

export default function MissionControlPage() {
  return (
    <Suspense fallback={<LoadingPanel label="Loading Mission Control" className="p-4" />}>
      <MissionControlView />
    </Suspense>
  );
}
