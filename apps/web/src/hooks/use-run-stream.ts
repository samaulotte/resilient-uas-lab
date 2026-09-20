"use client";

import { useEffect, useRef } from "react";

import { streamUrl } from "@/lib/api";
import { STALE_AFTER_MS, useLiveRun } from "@/stores/live-run";
import { useSettings } from "@/stores/settings";
import type { RunEvent, StreamMessage, TelemetrySample } from "@reslab/api-client";

const MAX_BACKOFF_MS = 20_000;
const BASE_BACKOFF_MS = 750;
const STALE_CHECK_MS = 5_000;

function parseMessage(data: unknown): StreamMessage | null {
  if (typeof data !== "string") return null;
  try {
    const parsed: unknown = JSON.parse(data);
    if (parsed && typeof parsed === "object" && "type" in parsed) {
      return parsed as StreamMessage;
    }
  } catch {
    return null;
  }
  return null;
}

/**
 * Subscribe to `WS /api/v1/runs/{id}/stream` and feed the live run store.
 *
 * Incoming telemetry can arrive many times per second, so samples and events are
 * buffered in refs and flushed into React state at the configured UI rate. The socket
 * reconnects with a capped exponential backoff and a reconnect snapshot replaces the
 * client state (events are deduplicated by sequence), so nothing is lost or doubled.
 */
export function useRunStream(runId: string | null, options: { onCompleted?: () => void } = {}) {
  const telemetryRate = useSettings((state) => state.telemetryRate);
  const onCompleted = options.onCompleted;
  const onCompletedRef = useRef(onCompleted);
  useEffect(() => {
    onCompletedRef.current = onCompleted;
  }, [onCompleted]);

  useEffect(() => {
    if (!runId) return;

    const store = useLiveRun;
    store.getState().start(runId);

    const eventBuffer: RunEvent[] = [];
    const sampleBuffer: TelemetrySample[] = [];
    let socket: WebSocket | null = null;
    let disposed = false;
    let attempt = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const flush = () => {
      if (eventBuffer.length === 0 && sampleBuffer.length === 0) return;
      const events = eventBuffer.splice(0, eventBuffer.length);
      const samples = sampleBuffer.splice(0, sampleBuffer.length);
      store.getState().ingest(events, samples);
    };

    const flushTimer = setInterval(flush, Math.round(1000 / telemetryRate));

    const staleTimer = setInterval(() => {
      const state = store.getState();
      if (state.finished || state.status !== "live") return;
      if (state.lastMessageAt !== null && Date.now() - state.lastMessageAt > STALE_AFTER_MS) {
        state.setStatus("stale");
      }
    }, STALE_CHECK_MS);

    const scheduleReconnect = () => {
      if (disposed) return;
      const state = store.getState();
      if (state.finished) {
        state.setStatus("closed");
        return;
      }
      attempt += 1;
      const delay = Math.min(MAX_BACKOFF_MS, BASE_BACKOFF_MS * 2 ** (attempt - 1));
      state.setStatus("reconnecting");
      reconnectTimer = setTimeout(connect, delay);
    };

    const handle = (message: StreamMessage) => {
      const state = store.getState();
      switch (message.type) {
        case "snapshot":
          flush();
          state.applySnapshot(message);
          state.setStatus(message.run.state === "COMPLETED" ? "closed" : "live");
          break;
        case "lifecycle":
          state.applyLifecycle(message);
          break;
        case "event":
          eventBuffer.push(message.event);
          state.touch();
          break;
        case "telemetry":
          sampleBuffer.push(...message.samples);
          state.touch();
          break;
        case "run_finished":
          flush();
          state.applyRunFinished(message);
          break;
        case "heartbeat":
          state.touch();
          if (state.status === "stale") state.setStatus("live");
          break;
        case "completed":
          flush();
          state.applyCompleted(message);
          onCompletedRef.current?.();
          break;
        default:
          break;
      }
    };

    function connect() {
      if (disposed) return;
      const state = store.getState();
      state.setStatus(attempt === 0 ? "connecting" : "reconnecting");
      let next: WebSocket;
      try {
        next = new WebSocket(streamUrl(runId ?? ""));
      } catch {
        state.setError("Could not open the live stream.");
        scheduleReconnect();
        return;
      }
      socket = next;

      next.onopen = () => {
        attempt = 0;
        store.getState().setError(null);
        store.getState().setStatus("live");
        store.getState().touch();
      };
      next.onmessage = (raw: MessageEvent<unknown>) => {
        const message = parseMessage(raw.data);
        if (message) handle(message);
      };
      next.onerror = () => {
        if (!store.getState().finished) {
          store.getState().setError("The live stream connection failed.");
        }
      };
      next.onclose = (closeEvent: CloseEvent) => {
        if (disposed) return;
        flush();
        const current = store.getState();
        if (current.finished || closeEvent.code === 1000) {
          current.setStatus("closed");
          return;
        }
        if (closeEvent.code === 1008) {
          current.setError("The run is not available for streaming.");
          current.setStatus("error");
          return;
        }
        scheduleReconnect();
      };
    }

    connect();

    return () => {
      disposed = true;
      clearInterval(flushTimer);
      clearInterval(staleTimer);
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (socket) {
        socket.onopen = null;
        socket.onmessage = null;
        socket.onerror = null;
        socket.onclose = null;
        if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
          socket.close(1000, "navigation");
        }
      }
    };
  }, [runId, telemetryRate]);
}
