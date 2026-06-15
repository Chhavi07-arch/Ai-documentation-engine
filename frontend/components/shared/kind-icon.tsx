import { Box, FileCode2, FunctionSquare, Hash } from "lucide-react";

import { cn } from "@/lib/utils";
import type { EntityKind } from "@/types";

const CONFIG: Record<EntityKind, { icon: typeof Box; className: string }> = {
  module: { icon: FileCode2, className: "text-sky-500" },
  class: { icon: Box, className: "text-violet-500" },
  function: { icon: FunctionSquare, className: "text-emerald-500" },
  method: { icon: Hash, className: "text-amber-500" },
};

/** Small colored icon distinguishing entity kinds across the UI. */
export function KindIcon({
  kind,
  className,
}: {
  kind: EntityKind;
  className?: string;
}) {
  const { icon: Icon, className: color } = CONFIG[kind];
  return <Icon className={cn("h-4 w-4", color, className)} />;
}
