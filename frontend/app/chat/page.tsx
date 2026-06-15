"use client";

import * as React from "react";
import { MessagesSquare } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/shared/states";
import { PageHeader } from "@/components/shared/page-header";
import { RepoSelect } from "@/components/shared/repo-select";
import { ChatPanel } from "@/features/chat/chat-panel";
import { useRepositories } from "@/hooks/use-docengine";

export default function ChatPage() {
  const repos = useRepositories();
  const [repoId, setRepoId] = React.useState<number | null>(null);

  React.useEffect(() => {
    if (repoId == null && repos.data?.length) {
      const ready = repos.data.find((r) => r.status === "ready") ?? repos.data[0];
      setRepoId(ready.id);
    }
  }, [repos.data, repoId]);

  return (
    <>
      <PageHeader
        title="AI Chat"
        description="Chat with an assistant grounded in your documentation — no hallucinations."
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

      {repos.isLoading ? (
        <Skeleton className="h-[70vh] w-full rounded-xl" />
      ) : repos.isError ? (
        <ErrorState message="Could not load repositories." onRetry={repos.refetch} />
      ) : !repos.data?.length ? (
        <EmptyState
          icon={MessagesSquare}
          title="No repositories to chat with"
          description="Ingest a repository and generate documentation first."
        />
      ) : repoId ? (
        <ChatPanel repositoryId={repoId} />
      ) : null}
    </>
  );
}
