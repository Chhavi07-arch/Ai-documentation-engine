"use client";

import * as React from "react";
import { Check, Copy } from "lucide-react";

import { cn } from "@/lib/utils";

/** A read-only source code panel with a copy-to-clipboard button. */
export function CodeBlock({
  code,
  language = "python",
  className,
}: {
  code: string;
  language?: string;
  className?: string;
}) {
  const [copied, setCopied] = React.useState(false);

  const copy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className={cn("group relative", className)}>
      <button
        onClick={copy}
        className="absolute right-3 top-3 rounded-md border border-border bg-background/80 p-1.5 text-muted-foreground opacity-0 transition-opacity hover:text-foreground group-hover:opacity-100"
        aria-label="Copy code"
      >
        {copied ? (
          <Check className="h-3.5 w-3.5 text-success" />
        ) : (
          <Copy className="h-3.5 w-3.5" />
        )}
      </button>
      <pre className="overflow-x-auto rounded-lg border border-border bg-muted/50 p-4">
        <code className={`language-${language} font-mono text-xs leading-relaxed`}>
          {code}
        </code>
      </pre>
    </div>
  );
}
