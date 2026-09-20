"use client";

import { Canvas } from "@react-three/fiber";
import { useEffect, useState } from "react";

import type { TwinFeed } from "@/components/twin/feed";
import { TwinScene } from "@/components/twin/scene";
import { Segmented } from "@/components/ui/segmented";
import { formatHeading, formatMetres, formatSpeed } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { CameraMode } from "@/stores/settings";
import type { PlannedPath, TelemetrySample } from "@reslab/api-client";

const CAMERA_OPTIONS = [
  { value: "chase" as const, label: "Chase", title: "Follow behind and above the vehicle" },
  { value: "orbit" as const, label: "Orbit", title: "Orbit around the vehicle with the mouse" },
  { value: "top" as const, label: "Top", title: "Look down on the whole mission area" },
  { value: "fpv" as const, label: "FPV", title: "Look along the vehicle heading" },
];

/** Poll the feed for readouts; the 3D scene itself never renders through React. */
function useFeedSample(feed: TwinFeed, intervalMs = 250): TelemetrySample | null {
  const [sample, setSample] = useState<TelemetrySample | null>(() => feed.getSample());
  useEffect(() => {
    const timer = setInterval(() => setSample(feed.getSample()), intervalMs);
    return () => clearInterval(timer);
  }, [feed, intervalMs]);
  return sample;
}

function Readout({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "ok" | "warn" | "bad" | "info";
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-[9.5px] uppercase tracking-[0.11em] text-dim">{label}</span>
      <span
        className={cn(
          "mono text-[11.5px]",
          tone === "ok" && "text-ok",
          tone === "warn" && "text-warn",
          tone === "bad" && "text-bad",
          tone === "info" && "text-info",
          !tone && "text-foreground",
        )}
      >
        {value}
      </span>
    </div>
  );
}

function OverlayCard({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "pointer-events-none absolute z-10 min-w-[152px] rounded-sm border border-border/80 bg-background/72 px-2 py-1.5 backdrop-blur-[2px]",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function TwinCanvas({
  feed,
  plannedPath,
  cameraMode,
  onCameraModeChange,
  reducedMotion,
}: {
  feed: TwinFeed;
  plannedPath: PlannedPath | null;
  cameraMode: CameraMode;
  onCameraModeChange: (mode: CameraMode) => void;
  reducedMotion: boolean;
}) {
  const sample = useFeedSample(feed);
  const groundSpeed = sample
    ? Math.hypot(sample.velocity.vx, sample.velocity.vy)
    : null;
  const navSource = sample?.navigation.source ?? "none";

  return (
    <div className="relative h-full w-full overflow-hidden bg-background">
      <Canvas
        camera={{ position: [70, 70, 150], fov: 50, near: 0.5, far: 3000 }}
        dpr={[1, 1.75]}
        gl={{ antialias: true, powerPreference: "high-performance" }}
        frameloop="always"
      >
        <TwinScene
          feed={feed}
          plannedPath={plannedPath}
          cameraMode={cameraMode}
          reducedMotion={reducedMotion}
        />
      </Canvas>

      <OverlayCard className="left-2 top-2">
        <p className="panel-title mb-1 text-[9px]">Position ENU</p>
        <Readout label="East x" value={formatMetres(sample?.position.x)} />
        <Readout label="North y" value={formatMetres(sample?.position.y)} />
        <Readout label="Up z" value={formatMetres(sample?.position.z)} />
      </OverlayCard>

      <OverlayCard className="left-2 bottom-2">
        <p className="panel-title mb-1 text-[9px]">Flight</p>
        <Readout label="Altitude" value={formatMetres(sample?.position.z)} />
        <Readout label="Ground speed" value={formatSpeed(groundSpeed)} />
        <Readout label="Heading" value={formatHeading(sample?.attitude.yaw)} />
      </OverlayCard>

      <OverlayCard className="right-2 bottom-2">
        <p className="panel-title mb-1 text-[9px]">Navigation</p>
        <Readout
          label="Source"
          value={navSource}
          tone={navSource === "gnss" ? "ok" : navSource === "dead_reckoning" ? "warn" : "bad"}
        />
        <Readout
          label="Position error"
          value={formatMetres(sample?.navigation.position_error, 2)}
          tone={
            !sample
              ? undefined
              : sample.navigation.position_error > 15
                ? "bad"
                : sample.navigation.position_error > 5
                  ? "warn"
                  : undefined
          }
        />
        <Readout
          label="Satellites"
          value={sample?.navigation.satellites != null ? String(sample.navigation.satellites) : "n/a"}
        />
      </OverlayCard>

      <div className="absolute right-2 top-2 z-10">
        <Segmented
          value={cameraMode}
          onValueChange={onCameraModeChange}
          options={CAMERA_OPTIONS}
          ariaLabel="Camera mode"
          size="xs"
          className="bg-background/80 backdrop-blur-[2px]"
        />
      </div>

      {!sample ? (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
          <span className="rounded-sm border border-border-strong bg-background/85 px-3 py-1.5 text-[12px] text-muted">
            Awaiting telemetry
          </span>
        </div>
      ) : null}
    </div>
  );
}
