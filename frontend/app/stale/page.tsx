"use client";

import * as React from "react";
import { CheckCircle2, Wand2, TriangleAlert } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState } from "@/components/shared/states";
import { PageHeader } from "@/components/shared/page-header";
import { RepoSelect } from "@/components/shared/repo-select";
import { SeverityBadge } from "@/components/shared/severity-badge";
import { DraftUpdateDialog } from "@/features/stale/draft-update-dialog";
import { useRepositories, useStaleDocs } from "@/hooks/use-docengine";
import { formatDate } from "@/lib/utils";
import type { StalenessFlag } from "@/types";

export default function StalePage() {
  const repos = useRepositories();
  const [repoId, setRepoId] = React.useState<number | null>(null);
  const flags = useStaleDocs(repoId ?? undefined);

  const [active, setActive] = React.useState<StalenessFlag | null>(null);
  const [dialogOpen, setDialogOpen] = React.useState(false);

  const openDraft = (flag: StalenessFlag) => {
    setActive(flag);
    setDialogOpen(true);
  };

  return (
    <>
      <PageHeader
        title="Stale Documentation Center"
        description="Documentation impacted by code changes, ranked by severity."
        actions={
          repos.data && repos.data.length > 0 ? (
            <RepoSelect
              repositories={repos.data}
              value={repoId}
              onChange={setRepoId}
              className="w-64"
            />
          ) : undefined
        }
      />

      {flags.isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      ) : flags.isError ? (
        <ErrorState message="Could not load staleness flags." onRetry={flags.refetch} />
      ) : flags.data!.length === 0 ? (
        <EmptyState
          icon={CheckCircle2}
          title="Everything looks up to date"
          description="Run “Detect changes” on a repository after code updates to surface stale documentation here."
        />
      ) : (
        <div className="space-y-3">
          {flags.data!.map((flag) => (
            <Card key={flag.id}>
              <CardContent className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <SeverityBadge severity={flag.severity} />
                    <Badge variant="muted">
                      <TriangleAlert className="h-3 w-3" />
                      {flag.change_type.replace(/_/g, " ")}
                    </Badge>
                  </div>
                  <p className="mt-2 break-all font-mono text-sm">
                    {flag.qualified_name}
                  </p>
                  <p className="mt-1 text-sm text-muted-foreground">{flag.reason}</p>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    Detected {formatDate(flag.created_at)}
                  </p>
                </div>
                <Button
                  variant="outline"
                  className="shrink-0"
                  onClick={() => openDraft(flag)}
                >
                  <Wand2 className="h-4 w-4" />
                  Draft update
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <DraftUpdateDialog
        flag={active}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      />
    </>
  );
}
