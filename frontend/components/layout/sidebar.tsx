"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookOpen,
  FolderGit2,
  LayoutDashboard,
  MessagesSquare,
  Settings,
  Sparkles,
  TriangleAlert,
} from "lucide-react";

import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/repositories", label: "Repositories", icon: FolderGit2 },
  { href: "/docs", label: "Documentation", icon: BookOpen },
  { href: "/stale", label: "Stale Center", icon: TriangleAlert },
  { href: "/chat", label: "AI Chat", icon: MessagesSquare },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r border-border bg-card/40 md:flex">
      <div className="flex h-16 items-center gap-2 border-b border-border px-6">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Sparkles className="h-4 w-4" />
        </div>
        <div className="leading-tight">
          <p className="text-sm font-semibold">DocEngine</p>
          <p className="text-[11px] text-muted-foreground">AI Documentation</p>
        </div>
      </div>

      <nav className="flex-1 space-y-1 p-3">
        {NAV.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              isActive(href)
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </Link>
        ))}
      </nav>

      <div className="border-t border-border p-4">
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          Ingest a GitHub repo, generate docs, and chat over them — all in one
          place.
        </p>
      </div>
    </aside>
  );
}
