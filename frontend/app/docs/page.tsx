"use client";

import * as React from "react";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { BookOpen } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/shared/states";
import { PageHeader } from "@/components/shared/page-header";
import { RepoSelect } from "@/components/shared/repo-select";
import { EntityList } from "@/features/docs/entity-list";
import { EntityDocView } from "@/features/docs/entity-doc-view";
import { useEntities, useRepositories } from "@/hooks/use-docengine";
import type { EntityRead } from "@/types";

export default function DocsPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full rounded-xl" />}>
      <DocsExplorer />
    </Suspense>
  );
}

function DocsExplorer() {
  const searchParams = useSearchParams();
  const repos = useRepositories();
  const [repoId, setRepoId] = React.useState<number | null>(null);
  const [selected, setSelected] = React.useState<EntityRead | null>(null);

  // Initialize the selected repo from the URL (?repo=) or the first ready one.
  React.useEffect(() => {
    if (repoId != null || !repos.data?.length) return;
    const fromUrl = Number(searchParams.get("repo"));
    const initial =
      (fromUrl && repos.data.find((r) => r.id === fromUrl)?.id) ??
      repos.data.find((r) => r.status === "ready")?.id ??
      repos.data[0].id;
    setRepoId(initial);
  }, [repos.data, repoId, searchParams]);

  const entities = useEntities(repoId ?? 0);

  // Default-select the first entity when the list loads or repo changes.
  React.useEffect(() => {
    if (entities.data?.length && !selected) {
      setSelected(entities.data[0]);
    }
  }, [entities.data, selected]);

  const onRepoChange = (id: number) => {
    setRepoId(id);
    setSelected(null);
  };

  return (
    <>
      <PageHeader
        title="Documentation Explorer"
        description="Browse generated documentation for every function, class, and module."
        actions={
          repos.data && repos.data.length > 0 ? (
            <RepoSelect
              repositories={repos.data}
              value={repoId}
              onChange={onRepoChange}
              className="w-64"
            />
          ) : undefined
        }
      />

      {repos.isLoading ? (
        <Skeleton className="h-96 w-full rounded-xl" />
      ) : repos.isError ? (
        <ErrorState message="Could not load repositories." onRetry={repos.refetch} />
      ) : !repos.data?.length ? (
        <EmptyState
          icon={BookOpen}
          title="No repositories yet"
          description="Ingest a repository and generate docs to explore them here."
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
          <Card className="h-fit">
            <CardContent className="p-4">
              {entities.isLoading ? (
                <div className="space-y-2">
                  {Array.from({ length: 8 }).map((_, i) => (
                    <Skeleton key={i} className="h-7 w-full" />
                  ))}
                </div>
              ) : entities.data?.length ? (
                <EntityList
                  entities={entities.data}
                  selectedId={selected?.id}
                  onSelect={setSelected}
                />
              ) : (
                <p className="px-2 py-6 text-center text-xs text-muted-foreground">
                  No entities found for this repository.
                </p>
              )}
            </CardContent>
          </Card>

          <div>
            {selected ? (
              <EntityDocView entity={selected} />
            ) : (
              <EmptyState
                icon={BookOpen}
                title="Select an entity"
                description="Choose a function, class, or module from the list to view its documentation."
              />
            )}
          </div>
        </div>
      )}
    </>
  );
}
