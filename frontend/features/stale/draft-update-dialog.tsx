"use client";

import * as React from "react";
import { Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DiffViewer } from "@/components/shared/diff-viewer";
import { Markdown } from "@/components/shared/markdown";
import { useDraftUpdate, useResolveFlag } from "@/hooks/use-docengine";
import { ApiError } from "@/lib/api";
import type { DraftUpdateResponse, StalenessFlag } from "@/types";

/**
 * Drafts an updated documentation version for a stale flag and shows the
 * unified diff against the current docs, plus a rendered preview.
 */
export function DraftUpdateDialog({
  flag,
  open,
  onOpenChange,
}: {
  flag: StalenessFlag | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [draft, setDraft] = React.useState<DraftUpdateResponse | null>(null);
  const draftUpdate = useDraftUpdate();
  const resolveFlag = useResolveFlag();

  // Generate the draft whenever a new flag is opened.
  React.useEffect(() => {
    if (!open || !flag) {
      setDraft(null);
      return;
    }
    let cancelled = false;
    draftUpdate
      .mutateAsync(flag.id)
      .then((res) => !cancelled && setDraft(res))
      .catch((err) => {
        toast.error("Could not draft update", {
          description: err instanceof ApiError ? err.message : "Unexpected error.",
        });
        onOpenChange(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, flag?.id]);

  const onResolve = async () => {
    if (!flag) return;
    try {
      await resolveFlag.mutateAsync(flag.id);
      toast.success("Flag resolved");
      onOpenChange(false);
    } catch {
      toast.error("Could not resolve flag");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            Draft documentation update
          </DialogTitle>
          <DialogDescription className="break-all font-mono text-xs">
            {flag?.qualified_name}
          </DialogDescription>
        </DialogHeader>

        {!draft ? (
          <div className="flex flex-col items-center justify-center py-16 text-sm text-muted-foreground">
            <Loader2 className="mb-3 h-6 w-6 animate-spin text-primary" />
            Drafting an updated version…
          </div>
        ) : (
          <>
            <Tabs defaultValue="diff">
              <TabsList>
                <TabsTrigger value="diff">Unified diff</TabsTrigger>
                <TabsTrigger value="preview">Preview</TabsTrigger>
              </TabsList>
              <TabsContent value="diff">
                <div className="max-h-[50vh] overflow-y-auto">
                  <DiffViewer diff={draft.unified_diff} />
                </div>
              </TabsContent>
              <TabsContent value="preview">
                <div className="max-h-[50vh] overflow-y-auto rounded-lg border border-border p-4">
                  <Markdown content={draft.drafted_markdown} />
                </div>
              </TabsContent>
            </Tabs>

            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                Drafted by {draft.generator === "ai" ? "AI" : "fallback"}
              </span>
              <div className="flex gap-2">
                <Button variant="ghost" onClick={() => onOpenChange(false)}>
                  Close
                </Button>
                <Button onClick={onResolve} disabled={resolveFlag.isPending}>
                  {resolveFlag.isPending && (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  )}
                  Mark resolved
                </Button>
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
