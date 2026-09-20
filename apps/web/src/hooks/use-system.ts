"use client";

import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api";

export function useSystemInfo() {
  return useQuery({
    queryKey: ["system"],
    queryFn: () => unwrap(api.GET("/api/v1/system")),
    refetchInterval: 15_000,
    staleTime: 10_000,
  });
}
