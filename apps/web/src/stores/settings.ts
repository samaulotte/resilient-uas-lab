"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type CameraMode = "chase" | "orbit" | "top" | "fpv";
export type TelemetryRate = 5 | 10 | 20;
export const DEMO_SPEEDS = [1, 2, 5, 10] as const;
export type DemoSpeed = (typeof DEMO_SPEEDS)[number];

export interface SettingsState {
  /** Simulation speed used by the Mission Control demo button. */
  demoSpeed: DemoSpeed;
  /** How often live telemetry is flushed from the socket buffer into React state. */
  telemetryRate: TelemetryRate;
  cameraMode: CameraMode;
  showLogEvents: boolean;
  reducedMotion: boolean;
  setDemoSpeed: (speed: DemoSpeed) => void;
  setTelemetryRate: (rate: TelemetryRate) => void;
  setCameraMode: (mode: CameraMode) => void;
  setShowLogEvents: (value: boolean) => void;
  setReducedMotion: (value: boolean) => void;
  reset: () => void;
}

const DEFAULTS = {
  demoSpeed: 1 as DemoSpeed,
  telemetryRate: 10 as TelemetryRate,
  cameraMode: "chase" as CameraMode,
  showLogEvents: false,
  reducedMotion: false,
};

export const useSettings = create<SettingsState>()(
  persist(
    (set) => ({
      ...DEFAULTS,
      setDemoSpeed: (demoSpeed) => set({ demoSpeed }),
      setTelemetryRate: (telemetryRate) => set({ telemetryRate }),
      setCameraMode: (cameraMode) => set({ cameraMode }),
      setShowLogEvents: (showLogEvents) => set({ showLogEvents }),
      setReducedMotion: (reducedMotion) => set({ reducedMotion }),
      reset: () => set({ ...DEFAULTS }),
    }),
    { name: "reslab.settings.v1", version: 1 },
  ),
);
