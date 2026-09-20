"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api";
import { ACTIVE_RUN_STATES } from "@/lib/states";
import type {
  RunCreateRequest,
  RunDetail,
  RunListResponse,
  RunState,
  RunSummary,
} from "@reslab/api-client";

export interface RunFilters {
  state?: RunState | null;
  scenario?: string | null;
  adapter?: string | null;
  result?: string | null;
  limit?: number;
  offset?: number;
}

function hasActive(runs: readonly RunSummary[]): boolean {
  return runs.some(
    (run) =>
      ACTIVE_RUN_STATES.includes(run.state) ||
      run.state === "CREATED" ||
      run.state === "VALIDATING",
  );
}

export function useRuns(filters: RunFilters = {}) {
  const query = {
    limit: filters.limit ?? 25,
    offset: filters.offset ?? 0,
    ...(filters.state ? { state: filters.state } : {}),
    ...(filters.scenario ? { scenario: filters.scenario } : {}),
    ...(filters.adapter ? { adapter: filters.adapter } : {}),
    ...(filters.result ? { result: filters.result } : {}),
  };
  return useQuery<RunListResponse>({
    queryKey: ["runs", query],
    queryFn: () => unwrap(api.GET("/api/v1/runs", { params: { query } })),
    refetchInterval: (q) => (q.state.data && hasActive(q.state.data.runs) ? 3_000 : 20_000),
    placeholderData: (previous) => previous,
  });
}

export function useRun(runId: string | null, options: { poll?: boolean } = {}) {
  return useQuery<RunDetail>({
    queryKey: ["run", runId],
    enabled: Boolean(runId),
    queryFn: () =>
      unwrap(api.GET("/api/v1/runs/{run_id}", { params: { path: { run_id: runId ?? "" } } })),
    refetchInterval: options.poll ? 4_000 : false,
  });
}

export function useRunEvents(runId: string | null, enabled = true, limit = 5000) {
  return useQuery({
    queryKey: ["run-events", runId, limit],
    enabled: Boolean(runId) && enabled,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/runs/{run_id}/events", {
          params: { path: { run_id: runId ?? "" }, query: { limit } },
        }),
      ),
    staleTime: 30_000,
  });
}

export function useRunTelemetry(runId: string | null, enabled = true, limit = 3000) {
  return useQuery({
    queryKey: ["run-telemetry", runId, limit],
    enabled: Boolean(runId) && enabled,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/runs/{run_id}/telemetry", {
          params: { path: { run_id: runId ?? "" }, query: { limit } },
        }),
      ),
    staleTime: 30_000,
  });
}

export function useRunMetrics(runId: string | null, enabled = true) {
  return useQuery({
    queryKey: ["run-metrics", runId],
    enabled: Boolean(runId) && enabled,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/runs/{run_id}/metrics", { params: { path: { run_id: runId ?? "" } } }),
      ),
    staleTime: 60_000,
    retry: 0,
  });
}

export function useCreateRun() {
  const client = useQueryClient();
  return useMutation<RunDetail, unknown, RunCreateRequest>({
    mutationFn: (body) => unwrap(api.POST("/api/v1/runs", { body })),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["runs"] });
      void client.invalidateQueries({ queryKey: ["scenarios"] });
    },
  });
}

export function useCancelRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) =>
      unwrap(api.POST("/api/v1/runs/{run_id}/cancel", { params: { path: { run_id: runId } } })),
    onSuccess: (_data, runId) => {
      void client.invalidateQueries({ queryKey: ["runs"] });
      void client.invalidateQueries({ queryKey: ["run", runId] });
    },
  });
}
