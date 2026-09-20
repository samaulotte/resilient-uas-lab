"use client";

import { useRef } from "react";

import { useElementWidth } from "@/hooks/use-element-size";
import { parseDuration } from "@/lib/duration";
import type { EventDraft } from "@/lib/scenario-document";
import { cn, formatMissionTime } from "@/lib/utils";

const HEIGHT = 74;
const AXIS_Y = 50;

/** Scenario events placed on the mission timeline. Clicking a marker selects the event. */
export function TimelineEditor({
  events,
  timeoutSeconds,
  selectedId,
  onSelect,
  names,
}: {
  events: readonly EventDraft[];
  timeoutSeconds: number;
  selectedId: string | null;
  onSelect: (id: string) => void;
  names: ReadonlyMap<string, string>;
}) {
  const container = useRef<HTMLDivElement>(null);
  const width = useElementWidth(container);
  const padding = 14;
  const plot = Math.max(60, width - padding * 2);
  const span = Math.max(timeoutSeconds, 1);
  const scale = (seconds: number) => padding + (Math.min(Math.max(seconds, 0), span) / span) * plot;

  const ticks: number[] = [];
  const step = span <= 120 ? 15 : span <= 300 ? 30 : 60;
  for (let t = 0; t <= span + 0.001; t += step) ticks.push(t);

  return (
    <div ref={container} className="w-full">
      {width > 0 ? (
        <svg
          width={width}
          height={HEIGHT}
          role="img"
          aria-label="Scenario event timeline"
          className="block"
        >
          <line
            x1={padding}
            x2={padding + plot}
            y1={AXIS_Y}
            y2={AXIS_Y}
            stroke="#2a3849"
            strokeWidth={1.5}
          />
          {ticks.map((tick) => (
            <g key={tick}>
              <line
                x1={scale(tick)}
                x2={scale(tick)}
                y1={AXIS_Y - 4}
                y2={AXIS_Y + 4}
                stroke="#2a3849"
              />
              <text
                x={scale(tick)}
                y={HEIGHT - 4}
                fontSize={9.5}
                className="mono"
                fill="#5d6b7a"
                textAnchor={tick === 0 ? "start" : tick + step > span ? "end" : "middle"}
              >
                {formatMissionTime(tick)}
              </text>
            </g>
          ))}
          {events.map((event, index) => {
            const at = parseDuration(event.at);
            if (at === null) return null;
            const x = scale(at);
            const duration = event.duration ? parseDuration(event.duration) : null;
            const selected = event.id === selectedId;
            const row = index % 2 === 0 ? 0 : 16;
            return (
              <g
                key={event.id}
                role="button"
                tabIndex={0}
                aria-label={`Select event ${event.id}`}
                onClick={() => onSelect(event.id)}
                onKeyDown={(keyEvent) => {
                  if (keyEvent.key === "Enter" || keyEvent.key === " ") onSelect(event.id);
                }}
                className="cursor-pointer"
              >
                {duration !== null ? (
                  <rect
                    x={x}
                    y={AXIS_Y - 6}
                    width={Math.max(2, scale(at + duration) - x)}
                    height={12}
                    fill={selected ? "#4fb3e8" : "#e0a52a"}
                    opacity={0.28}
                  />
                ) : null}
                <line
                  x1={x}
                  x2={x}
                  y1={AXIS_Y + 6}
                  y2={20 + row}
                  stroke={selected ? "#4fb3e8" : "#54677c"}
                  strokeWidth={selected ? 1.6 : 1}
                />
                <circle
                  cx={x}
                  cy={AXIS_Y}
                  r={selected ? 5 : 3.6}
                  fill={selected ? "#4fb3e8" : "#e0a52a"}
                  stroke="#070b10"
                  strokeWidth={1}
                >
                  <title>{`${event.id}: ${event.effect} on ${names.get(event.subsystem) ?? event.subsystem} at ${event.at}`}</title>
                </circle>
                <text
                  x={x}
                  y={16 + row}
                  fontSize={9.5}
                  className="mono"
                  fill={selected ? "#4fb3e8" : "#8b9bab"}
                  textAnchor="middle"
                >
                  {event.id.length > 18 ? `${event.id.slice(0, 17)}.` : event.id}
                </text>
              </g>
            );
          })}
        </svg>
      ) : (
        <div className={cn("h-[74px]")} />
      )}
    </div>
  );
}
