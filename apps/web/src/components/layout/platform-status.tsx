"use client";

import { useSystemInfo } from "@/hooks/use-system";
import { cn } from "@/lib/utils";

export function PlatformStatus() {
  const { data, isError, isLoading } = useSystemInfo();
  const onlineRunners = data?.runners.filter((r) => r.online).length ?? 0;
  const healthy = !!data && data.health.database && data.health.bus && data.health.artifact_store;
  const tone = isError ? "bad" : isLoading ? "dim" : healthy && onlineRunners > 0 ? "ok" : "warn";
  const label = isError
    ? "API UNREACHABLE"
    : isLoading
      ? "CONNECTING"
      : onlineRunners === 0
        ? "NO RUNNER ONLINE"
        : healthy
          ? "PLATFORM NOMINAL"
          : "PLATFORM DEGRADED";
  return (
    <div className="flex items-center gap-3 whitespace-nowrap text-[11px]">
      <span className="mono text-dim">v{data?.software_version ?? "0.1.0"}</span>
      <span
        className="flex items-center gap-1.5 text-muted"
        role="status"
        aria-live="polite"
        aria-label="Platform status"
        data-testid="platform-status"
      >
        <span
          aria-hidden
          className={cn(
            "inline-block h-2 w-2 rounded-full",
            tone === "ok" && "bg-ok",
            tone === "warn" && "bg-warn",
            tone === "bad" && "bg-bad",
            tone === "dim" && "bg-dim pulse-soft",
          )}
        />
        <span className="tracking-wide">{label}</span>
        {data && onlineRunners > 0 && (
          <span className="mono text-dim">
            {onlineRunners} runner{onlineRunners === 1 ? "" : "s"}
          </span>
        )}
      </span>
    </div>
  );
}
