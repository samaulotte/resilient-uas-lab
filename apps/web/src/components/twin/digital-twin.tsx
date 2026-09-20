"use client";

import dynamic from "next/dynamic";

import type { TwinFeed } from "@/components/twin/feed";
import type { CameraMode } from "@/stores/settings";
import type { PlannedPath } from "@reslab/api-client";

function TwinLoading() {
  return (
    <div className="grid-bg flex h-full w-full items-center justify-center bg-background">
      <span className="rounded-sm border border-border-strong bg-background/85 px-3 py-1.5 text-[12px] text-muted">
        Loading digital twin
      </span>
    </div>
  );
}

/** The 3D view is browser only and loaded on demand, never during server rendering. */
const LazyTwinCanvas = dynamic(
  () => import("@/components/twin/twin-canvas").then((module) => module.TwinCanvas),
  { ssr: false, loading: () => <TwinLoading /> },
);

export function DigitalTwin(props: {
  feed: TwinFeed;
  plannedPath: PlannedPath | null;
  cameraMode: CameraMode;
  onCameraModeChange: (mode: CameraMode) => void;
  reducedMotion: boolean;
}) {
  return <LazyTwinCanvas {...props} />;
}
