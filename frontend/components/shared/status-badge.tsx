import { CheckCircle2, Loader2, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { RepositoryStatus } from "@/types";

const CONFIG: Record<
  RepositoryStatus,
  { label: string; variant: "success" | "warning" | "destructive" | "muted"; spin?: boolean }
> = {
  pending: { label: "Pending", variant: "muted", spin: true },
  ingesting: { label: "Cloning", variant: "warning", spin: true },
  parsing: { label: "Parsing", variant: "warning", spin: true },
  generating: { label: "Generating", variant: "warning", spin: true },
  ready: { label: "Ready", variant: "success" },
  failed: { label: "Failed", variant: "destructive" },
};

/** Repository lifecycle badge with an animated icon while processing. */
export function StatusBadge({ status }: { status: RepositoryStatus }) {
  const { label, variant, spin } = CONFIG[status];
  const Icon = status === "ready" ? CheckCircle2 : status === "failed" ? XCircle : Loader2;
  return (
    <Badge variant={variant}>
      <Icon className={spin ? "h-3 w-3 animate-spin" : "h-3 w-3"} />
      {label}
    </Badge>
  );
}
