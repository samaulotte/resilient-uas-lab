"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api";
import type { ScenarioDetail, ScenarioSummary, ScenarioValidateResponse } from "@reslab/api-client";

export function useScenarios() {
  return useQuery<ScenarioSummary[]>({
    queryKey: ["scenarios"],
    queryFn: () => unwrap(api.GET("/api/v1/scenarios")),
    staleTime: 10_000,
  });
}

export function useScenario(name: string | null) {
  return useQuery<ScenarioDetail>({
    queryKey: ["scenario", name],
    enabled: Boolean(name),
    queryFn: () =>
      unwrap(api.GET("/api/v1/scenarios/{name}", { params: { path: { name: name ?? "" } } })),
  });
}

export function useValidateScenario() {
  return useMutation<ScenarioValidateResponse, unknown, string>({
    mutationFn: (document) =>
      unwrap(api.POST("/api/v1/scenarios/validate", { body: { document } })),
  });
}

/** Debounced live validation of an edited document. */
export function useScenarioValidation(document: string, enabled: boolean) {
  return useQuery<ScenarioValidateResponse>({
    queryKey: ["scenario-validate", document],
    enabled: enabled && document.trim().length > 0,
    queryFn: () => unwrap(api.POST("/api/v1/scenarios/validate", { body: { document } })),
    staleTime: 5 * 60_000,
    retry: 0,
  });
}

export function useSaveScenario() {
  const client = useQueryClient();
  return useMutation<ScenarioDetail, unknown, { document: string; overwrite: boolean }>({
    mutationFn: (body) => unwrap(api.POST("/api/v1/scenarios", { body })),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["scenarios"] });
    },
  });
}
