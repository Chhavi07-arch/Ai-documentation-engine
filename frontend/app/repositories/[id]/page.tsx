"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, FileCode2, GitBranch } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState, EmptyState } from "@/components/shared/states";
import { FileTree } from "@/components/shared/file-tree";
import { StatusBadge } from "@/components/shared/status-badge";
import { RepoActions } from "@/features/repositories/repo-actions";
import { useRepository } from "@/hooks/use-docengine";
import { toPercent } from "@/lib/utils";

export default function RepositoryDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const repoId = Number(params.id);
  const { data: repo, isLoading, isError, refetch } = useRepository(repoId);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-28 w-full rounded-xl" />
        <Skeleton className="h-96 w-full rounded-xl" />
      </div>
    );
  }

  if (isError || !repo) {
    return (
      <ErrorState message="Could not load this repository." onRetry={refetch} />
    );
  }

  const coverage = toPercent(
    repo.entity_count ? repo.documented_count / repo.entity_count : 0,
  );

  return (
    <>
      <Button variant="ghost" size="sm" asChild className="mb-4 -ml-2">
        <Link href="/repositories">
          <ArrowLeft className="h-4 w-4" /> Repositories
        </Link>
      </Button>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <h1 className="truncate text-2xl font-semibold tracking-tight">
              {repo.name}
            </h1>
            <StatusBadge status={repo.status} />
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{repo.full_name}</p>
        </div>
        <RepoActions repositoryId={repo.id} />
      </div>

      {repo.status === "failed" && repo.error_message && (
        <div className="mt-4 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {repo.error_message}
        </div>
      )}

      {/* Stats */}
      <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Files" value={repo.file_count} />
        <Stat label="Entities" value={repo.entity_count} />
        <Stat label="Documented" value={repo.documented_count} />
        <Stat label="Coverage" value={`${coverage}%`} />
      </div>

      {/* File tree */}
      <Card className="mt-8">
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="flex items-center gap-2 text-base">
            <FileCode2 className="h-4 w-4 text-muted-foreground" /> Source files
          </CardTitle>
          <Badge variant="muted">
            <GitBranch className="h-3 w-3" />
            {repo.default_branch}
          </Badge>
        </CardHeader>
        <CardContent>
          {repo.file_tree.length === 0 ? (
            <EmptyState
              title="No files indexed yet"
              description={
                repo.status === "ready"
                  ? "No supported source files were found in this repository."
                  : "Files appear here once ingestion completes."
              }
            />
          ) : (
            <FileTree
              nodes={repo.file_tree}
              onSelectFile={(_, path) => {
                router.push(
                  `/docs?repo=${repo.id}&path=${encodeURIComponent(path)}`,
                );
              }}
            />
          )}
        </CardContent>
      </Card>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <Card>
      <CardContent className="p-5">
        <p className="text-xs uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
        <p className="mt-1 text-2xl font-semibold">{value}</p>
      </CardContent>
    </Card>
  );
}
