import type { Metadata } from "next";
import { Suspense } from "react";

import { CompareView } from "@/app/compare/compare-view";
import { LoadingPanel } from "@/components/ui/feedback";

export const metadata: Metadata = { title: "Compare" };

export default function ComparePage() {
  return (
    <Suspense fallback={<LoadingPanel label="Loading comparison" className="p-4" />}>
      <CompareView />
    </Suspense>
  );
}
