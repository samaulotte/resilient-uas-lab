"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Panel, PanelBody, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { formatMissionTime } from "@/lib/utils";
import type { RunEvent, TelemetrySample } from "@reslab/api-client";

const MAX_POINTS = 320;

interface Point {
  t: number;
  altitude: number;
  positionError: number;
  progress: number;
  battery: number;
}

const AXIS = { stroke: "#2a3849", tick: { fill: "#5d6b7a", fontSize: 10 } } as const;

/** Recharts hands tooltip labels through as React nodes; only numbers are times. */
function missionTimeLabel(label: unknown): string {
  return typeof label === "number" ? formatMissionTime(label) : "";
}

const TOOLTIP_STYLE = {
  background: "#121b25",
  border: "1px solid #2a3849",
  borderRadius: 4,
  fontSize: 11,
  color: "#e6edf3",
} as const;

/** Compact telemetry traces next to the analysis, decimated to stay light. */
export function TelemetryChart({
  samples,
  events,
}: {
  samples: readonly TelemetrySample[];
  events: readonly RunEvent[];
}) {
  const points = useMemo<Point[]>(() => {
    if (samples.length === 0) return [];
    const stride = Math.max(1, Math.ceil(samples.length / MAX_POINTS));
    const result: Point[] = [];
    for (let index = 0; index < samples.length; index += stride) {
      const sample = samples[index];
      if (!sample) continue;
      result.push({
        t: Math.round(sample.t * 10) / 10,
        altitude: Math.round(sample.position.z * 10) / 10,
        positionError: Math.round(sample.navigation.position_error * 100) / 100,
        progress: Math.round(sample.mission.progress * 1000) / 10,
        battery: Math.round(sample.power.remaining * 1000) / 10,
      });
    }
    return result;
  }, [samples]);

  const injections = useMemo(
    () =>
      events
        .filter((event) => event.kind === "INJECTION_APPLIED")
        .map((event) => ({ t: event.simulation_time, id: event.scenario_event_id ?? "injection" })),
    [events],
  );

  if (points.length === 0) {
    return (
      <Panel>
        <PanelHeader>
          <PanelTitle>Telemetry</PanelTitle>
        </PanelHeader>
        <PanelBody>
          <p className="text-[12px] text-muted">This run recorded no telemetry.</p>
        </PanelBody>
      </Panel>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-2">
      <Panel>
        <PanelHeader>
          <PanelTitle>Altitude and position error</PanelTitle>
          <span className="ml-auto flex items-center gap-3 text-[10px]">
            <span className="flex items-center gap-1 text-info">
              <span aria-hidden className="inline-block h-0.5 w-3 bg-info" />
              altitude (m)
            </span>
            <span className="flex items-center gap-1 text-warn">
              <span aria-hidden className="inline-block h-0.5 w-3 bg-warn" />
              position error (m)
            </span>
          </span>
        </PanelHeader>
        <PanelBody className="p-2">
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={points} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
              <CartesianGrid stroke="#16202c" />
              <XAxis
                dataKey="t"
                type="number"
                domain={["dataMin", "dataMax"]}
                tickFormatter={(value: number) => formatMissionTime(value)}
                {...AXIS}
              />
              <YAxis {...AXIS} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                labelFormatter={(label) => missionTimeLabel(label)}
              />
              {injections.map((injection) => (
                <ReferenceLine
                  key={injection.id}
                  x={injection.t}
                  stroke="#e05252"
                  strokeDasharray="3 3"
                />
              ))}
              <Line
                type="monotone"
                dataKey="altitude"
                name="altitude"
                stroke="#4fb3e8"
                dot={false}
                strokeWidth={1.4}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="positionError"
                name="position error"
                stroke="#e0a52a"
                dot={false}
                strokeWidth={1.4}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader>
          <PanelTitle>Mission progress and battery</PanelTitle>
          <span className="ml-auto flex items-center gap-3 text-[10px]">
            <span className="flex items-center gap-1 text-info">
              <span aria-hidden className="inline-block h-0.5 w-3 bg-info" />
              progress (%)
            </span>
            <span className="flex items-center gap-1 text-muted">
              <span aria-hidden className="inline-block h-0.5 w-3 bg-dim" />
              battery (%)
            </span>
          </span>
        </PanelHeader>
        <PanelBody className="p-2">
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={points} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
              <CartesianGrid stroke="#16202c" />
              <XAxis
                dataKey="t"
                type="number"
                domain={["dataMin", "dataMax"]}
                tickFormatter={(value: number) => formatMissionTime(value)}
                {...AXIS}
              />
              <YAxis domain={[0, 100]} {...AXIS} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                labelFormatter={(label) => missionTimeLabel(label)}
              />
              {injections.map((injection) => (
                <ReferenceLine
                  key={injection.id}
                  x={injection.t}
                  stroke="#e05252"
                  strokeDasharray="3 3"
                />
              ))}
              <Line
                type="monotone"
                dataKey="progress"
                name="progress"
                stroke="#4fb3e8"
                dot={false}
                strokeWidth={1.4}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="battery"
                name="battery"
                stroke="#5d6b7a"
                dot={false}
                strokeWidth={1.4}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </PanelBody>
      </Panel>
    </div>
  );
}
