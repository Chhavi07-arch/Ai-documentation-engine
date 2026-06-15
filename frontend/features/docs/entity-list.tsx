"use client";

import * as React from "react";
import { Search } from "lucide-react";

import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { KindIcon } from "@/components/shared/kind-icon";
import { cn } from "@/lib/utils";
import type { EntityRead } from "@/types";

/** Searchable, scrollable list of code entities for the docs explorer. */
export function EntityList({
  entities,
  selectedId,
  onSelect,
}: {
  entities: EntityRead[];
  selectedId?: number | null;
  onSelect: (entity: EntityRead) => void;
}) {
  const [query, setQuery] = React.useState("");

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return entities;
    return entities.filter(
      (e) =>
        e.name.toLowerCase().includes(q) ||
        e.qualified_name.toLowerCase().includes(q),
    );
  }, [entities, query]);

  return (
    <div className="flex h-full flex-col">
      <div className="relative mb-3">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search entities…"
          className="pl-9"
        />
      </div>
      <ScrollArea className="h-[60vh] pr-2">
        <div className="space-y-0.5">
          {filtered.map((entity) => (
            <button
              key={entity.id}
              onClick={() => onSelect(entity)}
              className={cn(
                "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors",
                entity.id === selectedId
                  ? "bg-primary/10 text-primary"
                  : "hover:bg-accent hover:text-foreground",
              )}
            >
              <KindIcon kind={entity.kind} />
              <span className="truncate font-mono text-xs">{entity.name}</span>
              {!entity.has_docs && (
                <Badge variant="muted" className="ml-auto px-1.5 py-0 text-[10px]">
                  no docs
                </Badge>
              )}
            </button>
          ))}
          {filtered.length === 0 && (
            <p className="px-2 py-6 text-center text-xs text-muted-foreground">
              No entities match “{query}”.
            </p>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
