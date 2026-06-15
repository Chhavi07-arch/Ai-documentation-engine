"use client";

import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  Boxes,
  FolderGit2,
  Gauge,
  TriangleAlert,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorState } from "@/components/shared/states";
import { PageHeader } from "@/components/shared/page-header";
import { StatusBadge } from "@/components/shared/status-badge";
import { IngestDialog } from "@/features/repositories/ingest-dialog";
import { useRepositories, useStats } from "@/hooks/use-docengine";
import { formatDate, toPercent } from "@/lib/utils";

export default function DashboardPage() {
  const stats = useStats();
  const repos = useRepositories();

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Overview of your repositories, documentation coverage, and health."
        actions={<IngestDialog />}
      />

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {stats.isLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-xl" />
          ))
        ) : stats.isError ? (
          <div className="col-span-full">
            <ErrorState
              message="Could not load statistics."
              onRetry={() => stats.refetch()}
            />
          </div>
        ) : (
          <>
            <StatCard
              icon={FolderGit2}
              label="Repositories"
              value={stats.data!.repositories}
              hint={`${stats.data!.ready_repositories} ready`}
            />
            <StatCard
              icon={Boxes}
              label="Code entities"
              value={stats.data!.entities}
            />
            <StatCard
              icon={Gauge}
              label="Doc coverage"
              value={`${toPercent(stats.data!.documentation_coverage)}%`}
              hint={`${stats.data!.documented_entities} documented`}
            />
            <StatCard
              icon={TriangleAlert}
              label="Open flags"
              value={stats.data!.open_flags}
              hint="Stale docs"
            />
          </>
        )}
      </div>

      {/* Recent repositories */}
      <div className="mt-10">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Recent repositories</h2>
          <Button variant="ghost" size="sm" asChild>
            <Link href="/repositories">
              View all <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
        </div>

        {repos.isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-20 rounded-xl" />
            ))}
          </div>
        ) : repos.isError ? (
          <ErrorState
            message="Could not load repositories."
            onRetry={() => repos.refetch()}
          />
        ) : repos.data!.length === 0 ? (
          <EmptyState
            icon={FolderGit2}
            title="No repositories yet"
            description="Ingest your first GitHub repository to generate documentation."
            action={<IngestDialog />}
          />
        ) : (
          <div className="grid gap-3">
            {repos.data!.slice(0, 5).map((repo) => (
              <Link key={repo.id} href={`/repositories/${repo.id}`}>
                <Card className="transition-colors hover:border-primary/40 hover:bg-accent/30">
                  <CardContent className="flex items-center justify-between gap-4 p-4">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="truncate font-medium">{repo.full_name}</p>
                        <StatusBadge status={repo.status} />
                      </div>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {repo.entity_count} entities · {repo.documented_count}{" "}
                        documented · added {formatDate(repo.created_at)}
                      </p>
                    </div>
                    <Badge variant="muted">
                      <BookOpen className="h-3 w-3" />
                      {toPercent(
                        repo.entity_count
                          ? repo.documented_count / repo.entity_count
                          : 0,
                      )}
                      %
                    </Badge>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: typeof Gauge;
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-semibold">{value}</div>
        {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  );
}
