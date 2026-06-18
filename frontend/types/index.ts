/**
 * Shared API types. These mirror the backend Pydantic schemas so the data
 * contract is explicit and type-checked across the frontend.
 */

export type RepositoryStatus =
  | "pending"
  | "ingesting"
  | "parsing"
  | "generating"
  | "ready"
  | "failed";

export type EntityKind = "module" | "class" | "function" | "method";

export type StalenessSeverity =
  | "BROKEN"
  | "POTENTIALLY_OUTDATED"
  | "REVIEW_RECOMMENDED";

export type ChangeType =
  | "added"
  | "deleted"
  | "renamed"
  | "signature_changed"
  | "return_type_changed"
  | "parameters_changed"
  | "body_modified"
  | "docstring_changed"
  | "unchanged";

export interface Repository {
  id: number;
  name: string;
  full_name: string;
  url: string;
  default_branch: string;
  description: string | null;
  status: RepositoryStatus;
  error_message: string | null;
  file_count: number;
  entity_count: number;
  documented_count: number;
  created_at: string;
  updated_at: string;
}

export interface FileTreeNode {
  name: string;
  path: string;
  type: "dir" | "file";
  file_id: number | null;
  entity_count: number;
  children: FileTreeNode[];
}

export interface RepositoryDetail extends Repository {
  file_tree: FileTreeNode[];
}

export interface Parameter {
  name: string;
  annotation: string | null;
  default: string | null;
  kind: string;
}

export interface EntityRead {
  id: number;
  kind: EntityKind;
  name: string;
  qualified_name: string;
  relative_path: string;
  return_type: string | null;
  is_async: boolean;
  line_start: number;
  line_end: number;
  has_docs: boolean;
}

export interface EntityDetail extends EntityRead {
  repository_id: number;
  source_file_id: number;
  parent_name: string | null;
  signature: string;
  docstring: string | null;
  source_code: string;
  parameters: Parameter[];
  decorators: string[];
  imports: string[];
}

export interface Documentation {
  id: number;
  repository_id: number;
  entity_id: number;
  content_markdown: string;
  summary: string | null;
  version: number;
  generator: string;
  created_at: string;
  updated_at: string;
  entity: EntityRead | null;
}

export interface StalenessFlag {
  id: number;
  repository_id: number;
  entity_id: number | null;
  qualified_name: string;
  change_type: ChangeType;
  severity: StalenessSeverity;
  reason: string;
  resolved: boolean;
  created_at: string;
}

export interface EntityChange {
  qualified_name: string;
  kind: string;
  change_type: ChangeType;
  severity: StalenessSeverity | null;
  reason: string;
  renamed_from: string | null;
}

export interface DetectChangesResponse {
  repository_id: number;
  baseline_created: boolean;
  snapshot_id: number;
  changes: EntityChange[];
  flags_created: number;
}

export interface DraftUpdateResponse {
  flag_id: number;
  entity_id: number | null;
  qualified_name: string;
  original_markdown: string;
  drafted_markdown: string;
  unified_diff: string;
  generator: string;
}

export interface GenerateDocsResponse {
  repository_id: number;
  generated: number;
  skipped: number;
  failed: number;
  generator: string;
}

export interface RetrievedSource {
  qualified_name: string;
  relative_path: string;
  kind: string;
  score: number;
  excerpt: string;
}

export interface ChatResponse {
  answer: string;
  sources: RetrievedSource[];
  grounded: boolean;
}

export interface DashboardStats {
  repositories: number;
  ready_repositories: number;
  entities: number;
  documented_entities: number;
  open_flags: number;
  documentation_coverage: number;
}

export interface AppConfig {
  ai_enabled: boolean;
  model: string;
  embedding_mode: string;
  database?: string;
  auto_detect_enabled?: boolean;
  auto_detect_interval_seconds?: number;
  auto_detect_sync_remote?: boolean;
}
