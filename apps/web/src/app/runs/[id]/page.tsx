import type { Metadata } from "next";

import { RunDetailView } from "@/app/runs/[id]/run-detail-view";

export const metadata: Metadata = { title: "Run" };

export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <RunDetailView runId={id} />;
}
