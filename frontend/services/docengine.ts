/**
 * Domain API surface — one function per backend endpoint. Hooks call these so
 * the request shapes live in a single, testable place.
 */

import { api } from "@/lib/api";
import type {
  AppConfig,
  ChatResponse,
  DashboardStats,
  DetectChangesResponse,
  Documentation,
  DraftUpdateResponse,
  EntityDetail,
  EntityRead,
  GenerateDocsResponse,
  Repository,
  RepositoryDetail,
  StalenessFlag,
} from "@/types";

export const docengine = {
  // --- system ---
  getStats: () => api.get<DashboardStats>("/stats"),
  getConfig: () => api.get<AppConfig>("/config"),

  // --- repositories ---
  listRepositories: () => api.get<Repository[]>("/repositories"),
  getRepository: (id: number) =>
    api.get<RepositoryDetail>(`/repositories/${id}`),
  ingestRepository: (url: string) =>
    api.post<Repository>("/repositories/ingest", { url }),
  listEntities: (id: number, fileId?: number) =>
    api.get<EntityRead[]>(
      `/repositories/${id}/entities${fileId ? `?file_id=${fileId}` : ""}`,
    ),
  getEntity: (entityId: number) =>
    api.get<EntityDetail>(`/repositories/entities/${entityId}`),

  // --- documentation ---
  listDocs: (id: number) =>
    api.get<Documentation[]>(`/repositories/${id}/docs`),
  getDoc: (entityId: number) => api.get<Documentation>(`/docs/${entityId}`),
  generateDocs: (repositoryId: number, force = false) =>
    api.post<GenerateDocsResponse>("/generate-docs", {
      repository_id: repositoryId,
      force,
    }),

  // --- changes & staleness ---
  detectChanges: (repositoryId: number) =>
    api.post<DetectChangesResponse>("/detect-changes", {
      repository_id: repositoryId,
    }),
  // Pull the latest commits from GitHub first, THEN detect — so changes pushed
  // to the remote (the common case on a deployed instance) are picked up.
  syncAndDetect: (repositoryId: number) =>
    api.post<DetectChangesResponse>("/sync-and-detect", {
      repository_id: repositoryId,
    }),
  listStaleDocs: (repositoryId?: number) =>
    api.get<StalenessFlag[]>(
      `/stale-docs${repositoryId ? `?repository_id=${repositoryId}` : ""}`,
    ),
  draftUpdate: (flagId: number) =>
    api.post<DraftUpdateResponse>("/draft-update", { flag_id: flagId }),
  resolveFlag: (flagId: number) =>
    api.post<{ message: string }>(`/stale-docs/${flagId}/resolve`),

  // --- chat ---
  chat: (repositoryId: number, message: string, topK = 5) =>
    api.post<ChatResponse>("/chat", {
      repository_id: repositoryId,
      message,
      top_k: topK,
    }),
};
