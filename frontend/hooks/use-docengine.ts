/**
 * TanStack Query hooks wrapping the docengine API.
 *
 * Query keys are centralized in `queryKeys` so invalidation after mutations is
 * consistent and typo-proof.
 */

"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { docengine } from "@/services/docengine";
import type { RepositoryStatus } from "@/types";

export const queryKeys = {
  stats: ["stats"] as const,
  config: ["config"] as const,
  repositories: ["repositories"] as const,
  repository: (id: number) => ["repository", id] as const,
  entities: (id: number, fileId?: number) =>
    ["entities", id, fileId ?? null] as const,
  entity: (id: number) => ["entity", id] as const,
  docs: (id: number) => ["docs", id] as const,
  doc: (entityId: number) => ["doc", entityId] as const,
  staleDocs: (id?: number) => ["stale-docs", id ?? null] as const,
  // Prefix key: invalidating this matches every ["stale-docs", *] query
  // (all repo filters at once) — use it after detect/resolve mutations.
  staleDocsAll: ["stale-docs"] as const,
};

// Repositories that are still processing should be polled until ready/failed.
const ACTIVE_STATUSES: RepositoryStatus[] = [
  "pending",
  "ingesting",
  "parsing",
  "generating",
];

export function useStats() {
  return useQuery({ queryKey: queryKeys.stats, queryFn: docengine.getStats });
}

export function useConfig() {
  return useQuery({ queryKey: queryKeys.config, queryFn: docengine.getConfig });
}

export function useRepositories() {
  return useQuery({
    queryKey: queryKeys.repositories,
    queryFn: docengine.listRepositories,
    refetchInterval: (query) => {
      const data = query.state.data;
      const anyActive = data?.some((r) => ACTIVE_STATUSES.includes(r.status));
      return anyActive ? 2500 : false;
    },
  });
}

export function useRepository(id: number) {
  return useQuery({
    queryKey: queryKeys.repository(id),
    queryFn: () => docengine.getRepository(id),
    enabled: Number.isFinite(id) && id > 0,
    refetchInterval: (query) =>
      query.state.data && ACTIVE_STATUSES.includes(query.state.data.status)
        ? 2500
        : false,
  });
}

export function useEntities(id: number, fileId?: number) {
  return useQuery({
    queryKey: queryKeys.entities(id, fileId),
    queryFn: () => docengine.listEntities(id, fileId),
    enabled: Number.isFinite(id) && id > 0,
  });
}

export function useEntity(entityId: number) {
  return useQuery({
    queryKey: queryKeys.entity(entityId),
    queryFn: () => docengine.getEntity(entityId),
    enabled: Number.isFinite(entityId) && entityId > 0,
  });
}

export function useDocs(id: number) {
  return useQuery({
    queryKey: queryKeys.docs(id),
    queryFn: () => docengine.listDocs(id),
    enabled: Number.isFinite(id) && id > 0,
  });
}

export function useDoc(entityId: number) {
  return useQuery({
    queryKey: queryKeys.doc(entityId),
    queryFn: () => docengine.getDoc(entityId),
    enabled: Number.isFinite(entityId) && entityId > 0,
    retry: false,
  });
}

export function useStaleDocs(repositoryId?: number) {
  return useQuery({
    queryKey: queryKeys.staleDocs(repositoryId),
    queryFn: () => docengine.listStaleDocs(repositoryId),
  });
}

// --- mutations -------------------------------------------------------------

export function useIngestRepository() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (url: string) => docengine.ingestRepository(url),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.repositories });
      qc.invalidateQueries({ queryKey: queryKeys.stats });
    },
  });
}

export function useGenerateDocs(repositoryId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (force: boolean) => docengine.generateDocs(repositoryId, force),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.repository(repositoryId) });
      qc.invalidateQueries({ queryKey: queryKeys.docs(repositoryId) });
      qc.invalidateQueries({ queryKey: queryKeys.entities(repositoryId) });
      qc.invalidateQueries({ queryKey: queryKeys.stats });
    },
  });
}

export function useDetectChanges(repositoryId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => docengine.detectChanges(repositoryId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.staleDocsAll });
      qc.invalidateQueries({ queryKey: queryKeys.stats });
    },
  });
}

export function useDraftUpdate() {
  return useMutation({
    mutationFn: (flagId: number) => docengine.draftUpdate(flagId),
  });
}

export function useResolveFlag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (flagId: number) => docengine.resolveFlag(flagId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.staleDocsAll });
      qc.invalidateQueries({ queryKey: queryKeys.stats });
    },
  });
}
