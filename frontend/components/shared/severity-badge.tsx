import { AlertOctagon, AlertTriangle, Eye } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { StalenessSeverity } from "@/types";

const CONFIG: Record<
  StalenessSeverity,
  {
    label: string;
    variant: "destructive" | "warning" | "secondary";
    icon: typeof AlertOctagon;
  }
> = {
  BROKEN: { label: "Broken", variant: "destructive", icon: AlertOctagon },
  POTENTIALLY_OUTDATED: {
    label: "Potentially outdated",
    variant: "warning",
    icon: AlertTriangle,
  },
  REVIEW_RECOMMENDED: {
    label: "Review recommended",
    variant: "secondary",
    icon: Eye,
  },
};

/** A consistent, color-coded badge for documentation staleness severity. */
export function SeverityBadge({ severity }: { severity: StalenessSeverity }) {
  const { label, variant, icon: Icon } = CONFIG[severity];
  return (
    <Badge variant={variant}>
      <Icon className="h-3 w-3" />
      {label}
    </Badge>
  );
}
