"use client";

import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";
import type { Repository } from "@/types";

/**
 * Lightweight native-select repository picker used by pages that operate on a
 * single repository (docs explorer, chat, stale center).
 */
export function RepoSelect({
  repositories,
  value,
  onChange,
  className,
}: {
  repositories: Repository[];
  value: number | null;
  onChange: (id: number) => void;
  className?: string;
}) {
  return (
    <div className={cn("relative", className)}>
      <select
        value={value ?? ""}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-10 w-full appearance-none rounded-lg border border-input bg-background px-3 pr-9 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <option value="" disabled>
          Select a repository…
        </option>
        {repositories.map((repo) => (
          <option key={repo.id} value={repo.id}>
            {repo.full_name}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
    </div>
  );
}
