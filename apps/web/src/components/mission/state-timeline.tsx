"use client";

import { useRef } from "react";

import { useElementWidth } from "@/hooks/use-element-size";
import { COMPONENT_STATE, TONE_HEX } from "@/lib/states";
import { formatMissionTime } from "@/lib/utils";
import type { InjectionMarker, SubsystemTrack } from "@/lib/run-view";

const LABEL_WIDTH = 176;
const ROW_HEIGHT = 16;
const ROW_GAP = 3;
const AXIS_HEIGHT = 16;
const RIGHT_PAD = 12;

/** State colours are the tone colours; healthy states stay quiet, faults stand out. */
function segmentFill(state: string): { fill: string; opacity: number } {
  const style = COMPONENT_STATE[state as keyof typeof COMPONENT_STATE];
  const tone = style?.tone ?? "dim";
  const quiet = tone === "ok" || tone === "dim";
  return { fill: TONE_HEX[tone], opacity: quiet ? 0.26 : 0.8 };
}

function tickStep(duration: number): number {
  const candidates = [5, 10, 15, 30, 60, 120, 300, 600];
  for (const step of candidates) {
    if (duration / step <= 12) return step;
  }
  return 900;
}

export function StateTimeline({
  tracks,
  markers,
  now,
  duration,
}: {
  tracks: readonly SubsystemTrack[];
  markers: readonly InjectionMarker[];
  now: number;
  duration: number;
}) {
  const container = useRef<HTMLDivElement>(null);
  const width = useElementWidth(container);
  const plotWidth = Math.max(80, width - LABEL_WIDTH - RIGHT_PAD);
  const span = Math.max(duration, 1);
  const height = tracks.length * (ROW_HEIGHT + ROW_GAP) + AXIS_HEIGHT;
  const scale = (seconds: number) =>
    LABEL_WIDTH + (Math.min(Math.max(seconds, 0), span) / span) * plotWidth;
  const step = tickStep(span);
  const ticks: number[] = [];
  for (let t = 0; t <= span + 0.001; t += step) ticks.push(t);

  return (
    <div ref={container} className="w-full">
      {width > 0 ? (
        <svg
          width={width}
          height={height}
          role="img"
          aria-label="Subsystem state timeline over simulation time"
          className="block"
        >
          {ticks.map((tick) => (
            <line
              key={`grid-${tick}`}
              x1={scale(tick)}
              x2={scale(tick)}
              y1={0}
              y2={height - AXIS_HEIGHT}
              stroke="#16202c"
              strokeWidth={1}
            />
          ))}

          {tracks.map((track, rowIndex) => {
            const y = rowIndex * (ROW_HEIGHT + ROW_GAP);
            return (
              <g key={track.subsystem}>
                <text
                  x={0}
                  y={y + ROW_HEIGHT - 5}
                  className="mono"
                  fontSize={10.5}
                  fill={track.critical ? "#e6edf3" : "#8b9bab"}
                >
                  {track.name.length > 24 ? `${track.name.slice(0, 23)}.` : track.name}
                </text>
                {track.critical ? (
                  <text x={LABEL_WIDTH - 14} y={y + ROW_HEIGHT - 5} fontSize={9} fill="#e0a52a">
                    FC
                  </text>
                ) : null}
                <rect
                  x={LABEL_WIDTH}
                  y={y}
                  width={plotWidth}
                  height={ROW_HEIGHT}
                  fill="#0b1118"
                  stroke="#16202c"
                  strokeWidth={0.6}
                />
                {track.segments.map((segment, index) => {
                  const x = scale(segment.from);
                  const segmentWidth = Math.max(1.2, scale(segment.to) - x);
                  const { fill, opacity } = segmentFill(segment.state);
                  const label = COMPONENT_STATE[segment.state].label;
                  return (
                    <g key={`${track.subsystem}-${index}`}>
                      <rect x={x} y={y} width={segmentWidth} height={ROW_HEIGHT} fill={fill} opacity={opacity}>
                        <title>{`${track.name}: ${label} from ${formatMissionTime(segment.from)} to ${formatMissionTime(segment.to)}`}</title>
                      </rect>
                      {segmentWidth > label.length * 6.2 + 10 ? (
                        <text
                          x={x + 5}
                          y={y + ROW_HEIGHT - 5}
                          fontSize={9}
                          className="mono"
                          fill="#070b10"
                          fontWeight={600}
                          pointerEvents="none"
                        >
                          {label}
                        </text>
                      ) : null}
                    </g>
                  );
                })}
              </g>
            );
          })}

          {markers.map((marker, index) => (
            <g key={`marker-${index}-${marker.label}`}>
              <line
                x1={scale(marker.t)}
                x2={scale(marker.t)}
                y1={0}
                y2={height - AXIS_HEIGHT}
                stroke="#e05252"
                strokeWidth={1}
                strokeDasharray="3 3"
                opacity={0.75}
              />
              <polygon
                points={`${scale(marker.t) - 4},0 ${scale(marker.t) + 4},0 ${scale(marker.t)},6`}
                fill="#e05252"
              >
                <title>{`Injection ${marker.label} applied at ${formatMissionTime(marker.t)}`}</title>
              </polygon>
            </g>
          ))}

          <line
            x1={scale(now)}
            x2={scale(now)}
            y1={0}
            y2={height - AXIS_HEIGHT}
            stroke="#4fb3e8"
            strokeWidth={1.4}
          />
          <circle cx={scale(now)} cy={height - AXIS_HEIGHT} r={2.6} fill="#4fb3e8" />

          {ticks.map((tick) => (
            <text
              key={`tick-${tick}`}
              x={scale(tick)}
              y={height - 5}
              fontSize={9.5}
              className="mono"
              fill="#5d6b7a"
              textAnchor={tick === 0 ? "start" : tick + step > span ? "end" : "middle"}
            >
              {formatMissionTime(tick)}
            </text>
          ))}
        </svg>
      ) : (
        <div className="h-24" />
      )}
    </div>
  );
}
