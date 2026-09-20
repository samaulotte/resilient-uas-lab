"use client";

import { ExternalLink, Settings2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label, Switch } from "@/components/ui/field";
import { Notice } from "@/components/ui/feedback";
import { Panel, PanelBody, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { Segmented } from "@/components/ui/segmented";
import { API_BASE, apiUrl, streamUrl } from "@/lib/api";
import {
  DEMO_SPEEDS,
  useSettings,
  type CameraMode,
  type DemoSpeed,
  type TelemetryRate,
} from "@/stores/settings";

const CAMERA_OPTIONS = [
  { value: "chase" as const, label: "Chase" },
  { value: "orbit" as const, label: "Orbit" },
  { value: "top" as const, label: "Top" },
  { value: "fpv" as const, label: "FPV" },
];

const RATE_OPTIONS = [
  { value: "5", label: "5 Hz", title: "Lightest on the browser" },
  { value: "10", label: "10 Hz", title: "Default" },
  { value: "20", label: "20 Hz", title: "Smoothest readouts" },
];

function SettingRow({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-6 border-b border-border px-3 py-2.5 last:border-b-0">
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="text-[12px] text-foreground">{title}</span>
        <span className="text-[11px] leading-snug text-muted">{description}</span>
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

export function SettingsView() {
  const settings = useSettings();

  return (
    <div className="flex max-w-[980px] flex-col gap-2.5 p-4">
      <div className="flex items-center gap-3">
        <h1 className="flex items-center gap-1.5 text-[13px] font-semibold tracking-[0.04em]">
          <Settings2 size={14} className="text-info" aria-hidden />
          Settings
        </h1>
        <span className="text-[11px] text-dim">Stored in this browser only</span>
        <Button variant="ghost" size="xs" className="ml-auto" onClick={() => settings.reset()}>
          Restore defaults
        </Button>
      </div>

      <Panel>
        <PanelHeader>
          <PanelTitle>Preferences</PanelTitle>
        </PanelHeader>
        <PanelBody className="p-0">
          <SettingRow
            title="Default demo speed"
            description="Simulation speed used by the demo button on Mission Control. At 1x a demo run lasts about two and a half minutes."
          >
            <Segmented
              value={String(settings.demoSpeed)}
              onValueChange={(value) => settings.setDemoSpeed(Number(value) as DemoSpeed)}
              options={DEMO_SPEEDS.map((speed) => ({ value: String(speed), label: `${speed}x` }))}
              ariaLabel="Default demo speed"
            />
          </SettingRow>
          <SettingRow
            title="Telemetry update rate"
            description="How often buffered telemetry is flushed into the interface. The 3D view always renders at the display rate."
          >
            <Segmented
              value={String(settings.telemetryRate)}
              onValueChange={(value) => settings.setTelemetryRate(Number(value) as TelemetryRate)}
              options={RATE_OPTIONS}
              ariaLabel="Telemetry update rate"
            />
          </SettingRow>
          <SettingRow
            title="Default camera mode"
            description="Camera used when the digital twin opens."
          >
            <Segmented
              value={settings.cameraMode}
              onValueChange={(value) => settings.setCameraMode(value as CameraMode)}
              options={CAMERA_OPTIONS}
              ariaLabel="Default camera mode"
            />
          </SettingRow>
          <SettingRow
            title="Show LOG events"
            description="Include informational component logs in the live event feed. They are always available in the run event list."
          >
            <label className="flex items-center gap-2">
              <Switch
                checked={settings.showLogEvents}
                onCheckedChange={settings.setShowLogEvents}
                aria-label="Show LOG events"
              />
              <span className="text-[11px] text-muted">
                {settings.showLogEvents ? "shown" : "hidden"}
              </span>
            </label>
          </SettingRow>
          <SettingRow
            title="Reduced motion"
            description="Stop the rotor animation in the digital twin. The vehicle still follows telemetry."
          >
            <label className="flex items-center gap-2">
              <Switch
                checked={settings.reducedMotion}
                onCheckedChange={settings.setReducedMotion}
                aria-label="Reduced motion"
              />
              <span className="text-[11px] text-muted">
                {settings.reducedMotion ? "on" : "off"}
              </span>
            </label>
          </SettingRow>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader>
          <PanelTitle>Connection</PanelTitle>
          <Badge tone="dim" size="xs" className="ml-auto">
            read only
          </Badge>
        </PanelHeader>
        <PanelBody className="flex flex-col gap-2 p-3">
          <div className="grid grid-cols-[180px_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-[11.5px]">
            <Label>API base</Label>
            <span className="mono break-all text-foreground">
              {API_BASE || "same origin as this page"}
            </span>
            <Label>Run stream</Label>
            <span className="mono break-all text-foreground">{streamUrl("{run_id}")}</span>
            <Label>OpenAPI documentation</Label>
            <span>
              <a
                href={apiUrl("/api/docs")}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-info hover:underline"
              >
                {apiUrl("/api/docs")}
                <ExternalLink size={10} aria-hidden />
              </a>
            </span>
            <Label>OpenAPI schema</Label>
            <span>
              <a
                href={apiUrl("/api/openapi.json")}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-info hover:underline"
              >
                {apiUrl("/api/openapi.json")}
                <ExternalLink size={10} aria-hidden />
              </a>
            </span>
          </div>
          <Notice tone="warn">
            Authentication is not enabled in this local deployment. Anyone who can reach the API can
            create and cancel runs, so do not expose it outside a trusted network.
          </Notice>
        </PanelBody>
      </Panel>
    </div>
  );
}
