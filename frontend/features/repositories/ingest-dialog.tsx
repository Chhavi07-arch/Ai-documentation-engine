"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Github, Loader2, Plus } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useIngestRepository } from "@/hooks/use-docengine";
import { ApiError } from "@/lib/api";

/**
 * Dialog for ingesting a GitHub repository. On success it navigates to the new
 * repository's overview page, where progress is polled until ready.
 */
export function IngestDialog({ trigger }: { trigger?: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const [url, setUrl] = React.useState("");
  const router = useRouter();
  const ingest = useIngestRepository();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const repo = await ingest.mutateAsync(url.trim());
      toast.success("Repository queued", {
        description: "Cloning and parsing has started.",
      });
      setOpen(false);
      setUrl("");
      router.push(`/repositories/${repo.id}`);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Could not start ingestion.";
      toast.error("Ingestion failed", { description: message });
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button>
            <Plus className="h-4 w-4" />
            Add repository
          </Button>
        )}
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Ingest a GitHub repository</DialogTitle>
          <DialogDescription>
            Paste a public GitHub URL. Supports Python, JavaScript/TypeScript,
            Java, Go, Rust, Ruby, C/C++, C#, and PHP.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="relative">
            <Github className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              autoFocus
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://github.com/owner/repo"
              className="pl-9"
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!url.trim() || ingest.isPending}>
              {ingest.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Ingest
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
