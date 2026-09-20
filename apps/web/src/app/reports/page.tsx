import type { Metadata } from "next";
import { Suspense } from "react";

import { ReportsView } from "@/app/reports/reports-view";
import { LoadingPanel } from "@/components/ui/feedback";

export const metadata: Metadata = { title: "Reports" };

export default function ReportsPage() {
  return (
    <Suspense fallback={<LoadingPanel label="Loading reports" className="p-4" />}>
      <ReportsView />
    </Suspense>
  );
}
