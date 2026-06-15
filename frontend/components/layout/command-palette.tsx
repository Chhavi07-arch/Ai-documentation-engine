"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  BookOpen,
  FolderGit2,
  LayoutDashboard,
  MessagesSquare,
  Settings,
  TriangleAlert,
} from "lucide-react";

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { useRepositories } from "@/hooks/use-docengine";

const PAGES = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/repositories", label: "Repositories", icon: FolderGit2 },
  { href: "/docs", label: "Documentation", icon: BookOpen },
  { href: "/stale", label: "Stale Center", icon: TriangleAlert },
  { href: "/chat", label: "AI Chat", icon: MessagesSquare },
  { href: "/settings", label: "Settings", icon: Settings },
];

/**
 * Global command palette (⌘K / Ctrl+K). Jumps between pages and repositories —
 * the "command palette feel" expected of a modern docs tool.
 */
export function CommandPalette() {
  const [open, setOpen] = React.useState(false);
  const router = useRouter();
  const { data: repositories } = useRepositories();

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const go = (href: string) => {
    setOpen(false);
    router.push(href);
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex h-9 w-full max-w-xs items-center gap-2 rounded-lg border border-border bg-background px-3 text-sm text-muted-foreground transition-colors hover:bg-accent"
      >
        <span className="flex-1 text-left">Search…</span>
        <kbd className="pointer-events-none rounded border border-border bg-muted px-1.5 font-mono text-[10px]">
          ⌘K
        </kbd>
      </button>

      <CommandDialog open={open} onOpenChange={setOpen}>
        <CommandInput placeholder="Search pages and repositories…" />
        <CommandList>
          <CommandEmpty>No results found.</CommandEmpty>
          <CommandGroup heading="Pages">
            {PAGES.map(({ href, label, icon: Icon }) => (
              <CommandItem key={href} value={label} onSelect={() => go(href)}>
                <Icon className="h-4 w-4 text-muted-foreground" />
                {label}
              </CommandItem>
            ))}
          </CommandGroup>
          {repositories && repositories.length > 0 && (
            <CommandGroup heading="Repositories">
              {repositories.map((repo) => (
                <CommandItem
                  key={repo.id}
                  value={`repo ${repo.full_name}`}
                  onSelect={() => go(`/repositories/${repo.id}`)}
                >
                  <FolderGit2 className="h-4 w-4 text-muted-foreground" />
                  {repo.full_name}
                </CommandItem>
              ))}
            </CommandGroup>
          )}
        </CommandList>
      </CommandDialog>
    </>
  );
}
