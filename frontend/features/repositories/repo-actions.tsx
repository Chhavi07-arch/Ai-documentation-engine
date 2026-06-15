"use client";

import { useRouter } from "next/navigation";
import { BookOpen, Loader2, RefreshCw, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useDetectChanges, useGenerateDocs } from "@/hooks/use-docengine";
import { ApiError } from "@/lib/api";

/**
 * Primary actions for a repository: generate documentation, detect changes, and
 * jump into the docs explorer. Surfaces results via toasts.
 */
export function RepoActions({ repositoryId }: { repositoryId: number }) {
  const router = useRouter();
  const generate = useGenerateDocs(repositoryId);
  const detect = useDetectChanges(repositoryId);

  const onGenerate = async () => {
    try {
      const res = await generate.mutateAsync(false);
      toast.success("Documentation generated", {
        description: `${res.generated} entities documented (${res.generator}).`,
      });
    } catch (err) {
      toast.error("Generation failed", {
        description: err instanceof ApiError ? err.message : "Unexpected error.",
      });
    }
  };

  const onDetect = async () => {
    try {
      const res = await detect.mutateAsync();
      if (res.baseline_created) {
        toast.success("Baseline snapshot created", {
          description: "Future detections will compare against this snapshot.",
        });
      } else {
        toast.success("Change detection complete", {
          description: `${res.changes.length} changes, ${res.flags_created} flags created.`,
        });
      }
    } catch (err) {
      toast.error("Detection failed", {
        description: err instanceof ApiError ? err.message : "Unexpected error.",
      });
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button onClick={onGenerate} disabled={generate.isPending}>
        {generate.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Sparkles className="h-4 w-4" />
        )}
        Generate docs
      </Button>
      <Button variant="outline" onClick={onDetect} disabled={detect.isPending}>
        {detect.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <RefreshCw className="h-4 w-4" />
        )}
        Detect changes
      </Button>
      <Button
        variant="ghost"
        onClick={() => router.push(`/docs?repo=${repositoryId}`)}
      >
        <BookOpen className="h-4 w-4" />
        Open docs
      </Button>
    </div>
  );
}
