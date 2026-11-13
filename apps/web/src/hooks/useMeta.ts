import { useQuery } from "@tanstack/react-query";

import { queries } from "@/lib/api";

export function useMeta() {
  return useQuery({
    queryKey: ["meta"],
    queryFn: queries.meta,
    staleTime: 60_000,
    retry: 1,
  });
}

export function useReadiness() {
  return useQuery({
    queryKey: ["readiness"],
    queryFn: queries.ready,
    refetchInterval: 30_000,
    retry: 0,
    staleTime: 10_000,
  });
}

export function useCoverage() {
  return useQuery({
    queryKey: ["coverage"],
    queryFn: queries.coverage,
    refetchInterval: 60_000,
    retry: 1,
    staleTime: 30_000,
  });
}

export function useProviderHealth() {
  return useQuery({
    queryKey: ["provider-health"],
    queryFn: queries.providerHealth,
    refetchInterval: 60_000,
    retry: 1,
    staleTime: 30_000,
  });
}
