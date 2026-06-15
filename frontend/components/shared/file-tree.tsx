"use client";

import * as React from "react";
import { ChevronRight, FileCode2, Folder, FolderOpen } from "lucide-react";

import { cn } from "@/lib/utils";
import type { FileTreeNode } from "@/types";

/**
 * Recursive, collapsible file tree resembling a modern docs/IDE sidebar.
 * Selecting a file calls `onSelectFile` with its id.
 */
export function FileTree({
  nodes,
  selectedFileId,
  onSelectFile,
}: {
  nodes: FileTreeNode[];
  selectedFileId?: number | null;
  onSelectFile?: (fileId: number, path: string) => void;
}) {
  return (
    <div className="space-y-0.5 text-sm">
      {nodes.map((node) => (
        <TreeItem
          key={node.path}
          node={node}
          depth={0}
          selectedFileId={selectedFileId}
          onSelectFile={onSelectFile}
        />
      ))}
    </div>
  );
}

function TreeItem({
  node,
  depth,
  selectedFileId,
  onSelectFile,
}: {
  node: FileTreeNode;
  depth: number;
  selectedFileId?: number | null;
  onSelectFile?: (fileId: number, path: string) => void;
}) {
  const [open, setOpen] = React.useState(depth < 1);
  const pad = { paddingLeft: `${depth * 12 + 8}px` };

  if (node.type === "dir") {
    return (
      <div>
        <button
          onClick={() => setOpen((v) => !v)}
          style={pad}
          className="flex w-full items-center gap-1.5 rounded-md py-1.5 pr-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <ChevronRight
            className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-90")}
          />
          {open ? (
            <FolderOpen className="h-4 w-4 text-sky-500" />
          ) : (
            <Folder className="h-4 w-4 text-sky-500" />
          )}
          <span className="truncate">{node.name}</span>
        </button>
        {open && (
          <div>
            {node.children.map((child) => (
              <TreeItem
                key={child.path}
                node={child}
                depth={depth + 1}
                selectedFileId={selectedFileId}
                onSelectFile={onSelectFile}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  const selected = node.file_id != null && node.file_id === selectedFileId;
  return (
    <button
      onClick={() => node.file_id != null && onSelectFile?.(node.file_id, node.path)}
      style={pad}
      className={cn(
        "flex w-full items-center gap-1.5 rounded-md py-1.5 pr-2 text-left transition-colors",
        selected
          ? "bg-primary/10 text-primary"
          : "text-foreground/80 hover:bg-accent hover:text-foreground",
      )}
    >
      <span className="w-3.5" />
      <FileCode2 className="h-4 w-4 shrink-0 text-muted-foreground" />
      <span className="truncate">{node.name}</span>
      {node.entity_count > 0 && (
        <span className="ml-auto rounded bg-muted px-1.5 text-[10px] text-muted-foreground">
          {node.entity_count}
        </span>
      )}
    </button>
  );
}
