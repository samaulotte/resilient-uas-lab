"use client";

import * as SliderPrimitive from "@radix-ui/react-slider";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Pause, Play, RotateCcw } from "lucide-react";

import { BlastRadius } from "@/components/mission/blast-radius";
import { ActiveAlerts, EventFeed } from "@/components/mission/event-feed";
import { StateTimeline } from "@/components/mission/state-timeline";
import { SystemPanel } from "@/components/mission/system-panel";
import { DigitalTwin } from "@/components/twin/digital-twin";
import type { TwinFeed } from "@/components/twin/feed";
import { Button } from "@/components/ui/button";
import { Panel, PanelBody, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { Segmented } from "@/components/ui/segmented";
import { activeAlerts } from "@/lib/events";
import {
  buildTimeline,
  currentHealth,
  injectionMarkers,
  liveContainmentKpis,
} from "@/lib/run-view";
import {
  componentMap,
  componentNameMap,
  groupByDomain,
  missionFlightBoundary,
} from "@/lib/topology";
import { formatMissionTime } from "@/lib/utils";
import { useSettings } from "@/stores/settings";
import type { PlannedPath, RunEvent, SystemTopology, TelemetrySample } from "@reslab/api-client";

const SPEED_OPTIONS = [
  { value: "1", label: "1x" },
  { value: "2", label: "2x" },
  { value: "5", label: "5x" },
  { value: "10", label: "10x" },
];

function indexAt(samples: readonly TelemetrySample[], time: number): number {
  let low = 0;
  let high = samples.length;
  while (low < high) {
    const mid = (low + high) >> 1;
    const sample = samples[mid];
    if (sample !== undefined && sample.t <= time) low = mid + 1;
    else high = mid;
  }
  return low;
}

/** Mission Control layout replayed from stored telemetry and events. */
export function ReplayTab({
  samples,
  events,
  plannedPath,
  topology,
  duration,
}: {
  samples: readonly TelemetrySample[];
  events: readonly RunEvent[];
  plannedPath: PlannedPath | null;
  topology: SystemTopology | undefined;
  duration: number;
}) {
  const cameraMode = useSettings((state) => state.cameraMode);
  const setCameraMode = useSettings((state) => state.setCameraMode);
  const reducedMotion = useSettings((state) => state.reducedMotion);

  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState("1");

  const cursorRef = useRef(0);
  const trailRef = useRef<readonly TelemetrySample[]>([]);
  const sampleRef = useRef<TelemetrySample | null>(null);
  const generationRef = useRef(0);

  const applyCursor = useCallback(
    (time: number, seek: boolean) => {
      const clamped = Math.min(Math.max(time, 0), duration);
      cursorRef.current = clamped;
      const index = indexAt(samples, clamped);
      trailRef.current = samples.slice(0, index);
      sampleRef.current = samples[Math.max(0, index - 1)] ?? null;
      if (seek) generationRef.current += 1;
      return clamped;
    },
    [samples, duration],
  );

  // Position the replay at the start of the recording once the samples are known.
  useEffect(() => {
    applyCursor(cursorRef.current, true);
  }, [applyCursor]);

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let last = performance.now();
    let published = 0;
    const factor = Number(speed);
    const tick = (now: number) => {
      const delta = (now - last) / 1000;
      last = now;
      const next = applyCursor(cursorRef.current + delta * factor, false);
      if (now - published > 100) {
        published = now;
        setCursor(next);
      }
      if (next >= duration) {
        setCursor(next);
        setPlaying(false);
        return;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, speed, duration, applyCursor]);

  const feed = useMemo<TwinFeed>(
    () => ({
      getSample: () => sampleRef.current,
      getTrail: () => trailRef.current,
      getGeneration: () => generationRef.current,
    }),
    [],
  );

  const components = useMemo(() => componentMap(topology), [topology]);
  const names = useMemo(() => componentNameMap(topology), [topology]);
  const groups = useMemo(() => groupByDomain(topology), [topology]);
  const boundary = useMemo(() => missionFlightBoundary(topology), [topology]);

  const visibleEvents = useMemo(
    () => events.filter((event) => event.simulation_time <= cursor),
    [events, cursor],
  );
  const sample = samples[Math.max(0, indexAt(samples, cursor) - 1)] ?? null;
  const health = useMemo(() => currentHealth(sample, visibleEvents), [sample, visibleEvents]);
  const alerts = useMemo(() => activeAlerts(sample, names), [sample, names]);
  const tracks = useMemo(
    () => buildTimeline(visibleEvents, components, Math.max(cursor, 1)),
    [visibleEvents, components, cursor],
  );
  const markers = useMemo(() => injectionMarkers(visibleEvents), [visibleEvents]);
  const containment = useMemo(
    () => liveContainmentKpis(visibleEvents, components),
    [visibleEvents, components],
  );
  const feedEvents = useMemo(() => [...visibleEvents].reverse().slice(0, 80), [visibleEvents]);

  if (samples.length === 0) {
    return (
      <p className="px-3 py-6 text-[12px] text-muted">
        This run recorded no telemetry, so there is nothing to replay.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="panel flex items-center gap-3 px-3 py-2">
        <Button
          variant="primary"
          size="sm"
          onClick={() => {
            if (cursorRef.current >= duration) {
              setCursor(applyCursor(0, true));
            }
            setPlaying(!playing);
          }}
          aria-label={playing ? "Pause replay" : "Play replay"}
        >
          {playing ? <Pause size={11} aria-hidden /> : <Play size={11} aria-hidden />}
          {playing ? "Pause" : "Play"}
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            setPlaying(false);
            setCursor(applyCursor(0, true));
          }}
          aria-label="Restart replay"
        >
          <RotateCcw size={11} aria-hidden />
          Restart
        </Button>
        <span className="mono w-[62px] text-[12px] text-foreground">
          {formatMissionTime(cursor)}
        </span>
        <SliderPrimitive.Root
          className="relative flex h-4 flex-1 cursor-pointer items-center"
          value={[cursor]}
          min={0}
          max={duration}
          step={0.1}
          aria-label="Replay position"
          onValueChange={(value) => {
            const next = value[0] ?? 0;
            setPlaying(false);
            setCursor(applyCursor(next, true));
          }}
        >
          <SliderPrimitive.Track className="relative h-1 w-full grow overflow-hidden rounded-full bg-panel-3">
            <SliderPrimitive.Range className="absolute h-full bg-info" />
          </SliderPrimitive.Track>
          <SliderPrimitive.Thumb className="block h-3 w-3 rounded-full border border-info bg-background" />
        </SliderPrimitive.Root>
        <span className="mono text-[11px] text-dim">{formatMissionTime(duration)}</span>
        <Segmented
          value={speed}
          onValueChange={setSpeed}
          options={SPEED_OPTIONS}
          ariaLabel="Replay speed"
          size="xs"
        />
      </div>

      <div className="grid h-[380px] grid-cols-[250px_minmax(300px,1fr)_300px] gap-2">
        <Panel>
          <PanelHeader>
            <PanelTitle>System</PanelTitle>
          </PanelHeader>
          <PanelBody className="overflow-y-auto p-2">
            <SystemPanel groups={groups} health={health} />
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader>
            <PanelTitle>Digital twin</PanelTitle>
          </PanelHeader>
          <PanelBody className="p-0">
            <DigitalTwin
              feed={feed}
              plannedPath={plannedPath}
              cameraMode={cameraMode}
              onCameraModeChange={setCameraMode}
              reducedMotion={reducedMotion}
            />
          </PanelBody>
        </Panel>
        <div className="flex min-h-0 flex-col gap-2">
          <Panel className="shrink-0">
            <PanelHeader>
              <PanelTitle>Active events</PanelTitle>
            </PanelHeader>
            <PanelBody className="max-h-[120px] overflow-y-auto p-2">
              <ActiveAlerts alerts={alerts} />
            </PanelBody>
          </Panel>
          <Panel className="min-h-0 flex-1">
            <PanelHeader>
              <PanelTitle>Events up to cursor</PanelTitle>
              <span className="ml-auto text-[10px] text-dim">{visibleEvents.length}</span>
            </PanelHeader>
            <PanelBody className="min-h-0 overflow-y-auto p-0">
              <EventFeed events={feedEvents} emptyLabel="No event before this time" dense />
            </PanelBody>
          </Panel>
        </div>
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)_300px] gap-2">
        <Panel>
          <PanelHeader>
            <PanelTitle>System state timeline</PanelTitle>
          </PanelHeader>
          <PanelBody className="overflow-x-hidden p-2">
            {tracks.length === 0 ? (
              <p className="px-1 py-4 text-[12px] text-muted">
                No subsystem state change before this time.
              </p>
            ) : (
              <StateTimeline tracks={tracks} markers={markers} now={cursor} duration={duration} />
            )}
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader>
            <PanelTitle>Blast radius</PanelTitle>
          </PanelHeader>
          <PanelBody className="overflow-y-auto p-2">
            <BlastRadius
              components={components}
              injected={new Set(containment.injectedComponents)}
              affected={new Set(containment.affectedComponents)}
              health={health}
              boundary={boundary}
              affectedDomains={containment.affectedDomains}
              flightDomainAffected={containment.flightDomainAffected}
            />
          </PanelBody>
        </Panel>
      </div>
    </div>
  );
}
