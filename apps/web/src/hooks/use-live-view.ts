"use client";

import { useEffect, useRef, useState } from "react";

import { useLiveRun, type LiveRunState } from "@/stores/live-run";

/**
 * Subscribe to the live run store but re-render at most every `ms`.
 *
 * Telemetry is flushed into the store about ten times per second; panels that only
 * need a readable value do not need to re-render that often. The 3D scene bypasses
 * React entirely and reads the store inside its frame loop.
 */
export function useLiveRunThrottled<T>(selector: (state: LiveRunState) => T, ms = 400): T {
  const selectorRef = useRef(selector);
  useEffect(() => {
    selectorRef.current = selector;
  });
  const [value, setValue] = useState<T>(() => selector(useLiveRun.getState()));
  useEffect(() => {
    let last = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const apply = () => {
      last = Date.now();
      setValue(() => selectorRef.current(useLiveRun.getState()));
    };
    apply();
    const unsubscribe = useLiveRun.subscribe(() => {
      const elapsed = Date.now() - last;
      if (elapsed >= ms) {
        apply();
      } else if (timer === null) {
        timer = setTimeout(() => {
          timer = null;
          apply();
        }, ms - elapsed);
      }
    });
    return () => {
      unsubscribe();
      if (timer !== null) clearTimeout(timer);
    };
  }, [ms]);
  return value;
}
