"use client";

import Link from "next/link";
import { Github } from "lucide-react";

import { Button } from "@/components/ui/button";
import { CommandPalette } from "@/components/layout/command-palette";
import { ThemeToggle } from "@/components/layout/theme-toggle";

/** Sticky top bar with the command palette, GitHub link, and theme toggle. */
export function Topbar() {
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-4 border-b border-border bg-background/80 px-4 backdrop-blur md:px-8">
      <div className="md:hidden">
        <Link href="/" className="text-sm font-semibold">
          DocEngine
        </Link>
      </div>
      <div className="flex flex-1 justify-center md:justify-start">
        <CommandPalette />
      </div>
      <div className="flex items-center gap-1">
        <Button variant="ghost" size="icon" asChild aria-label="OpenRouter">
          <a href="https://openrouter.ai" target="_blank" rel="noreferrer">
            <Github className="h-4 w-4" />
          </a>
        </Button>
        <ThemeToggle />
      </div>
    </header>
  );
}
