"use client";

import Link from "next/link";
import { FolderGit2 } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorState } from "@/components/shared/states";
import { PageHeader } from "@/components/shared/page-header";
import { StatusBadge } from "@/components/shared/status-badge";
import { IngestDialog } from "@/features/repositories/ingest-dialog";
import { useRepositories } from "@/hooks/use-docengine";
import { formatDate, toPercent } from "@/lib/utils";

export default function RepositoriesPage() {
  const { data, isLoading, isError, refetch } = useRepositories();

  return (
    <>
      <PageHeader
        title="Repositories"
        description="Every repository you've ingested into the documentation engine."
        actions={<IngestDialog />}
      />

      {isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-xl" />
          ))}
        </div>
      ) : isError ? (
        <ErrorState message="Could not load repositories." onRetry={refetch} />
      ) : data!.length === 0 ? (
        <EmptyState
          icon={FolderGit2}
          title="No repositories yet"
          description="Ingest your first GitHub repository to get started."
          action={<IngestDialog />}
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {data!.map((repo) => (
            <Link key={repo.id} href={`/repositories/${repo.id}`}>
              <Card className="h-full transition-colors hover:border-primary/40 hover:bg-accent/30">
                <CardContent className="p-5">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate font-medium">{repo.name}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        {repo.full_name}
                      </p>
                    </div>
                    <StatusBadge status={repo.status} />
                  </div>

                  {repo.error_message && (
                    <p className="mt-3 line-clamp-2 text-xs text-destructive">
                      {repo.error_message}
                    </p>
                  )}

                  <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <Badge variant="muted">{repo.file_count} files</Badge>
                    <Badge variant="muted">{repo.entity_count} entities</Badge>
                    <Badge variant="muted">
                      {toPercent(
                        repo.entity_count
                          ? repo.documented_count / repo.entity_count
                          : 0,
                      )}
                      % documented
                    </Badge>
                  </div>

                  <p className="mt-3 text-[11px] text-muted-foreground">
                    Added {formatDate(repo.created_at)}
                  </p>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
