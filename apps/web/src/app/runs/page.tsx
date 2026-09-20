import type { Metadata } from "next";
import { Suspense } from "react";

import { RunsView } from "@/app/runs/runs-view";
import { LoadingPanel } from "@/components/ui/feedback";

export const metadata: Metadata = { title: "Runs" };

export default function RunsPage() {
  return (
    <Suspense fallback={<LoadingPanel label="Loading runs" className="p-4" />}>
      <RunsView />
    </Suspense>
  );
}
