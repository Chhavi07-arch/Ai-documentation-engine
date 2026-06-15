import { cn } from "@/lib/utils";

/**
 * Render a unified diff (as produced by Python's difflib) with colored,
 * line-numbered hunks. Purely presentational — no parsing of the original docs
 * is required because the backend already returns a unified diff string.
 */
export function DiffViewer({ diff }: { diff: string }) {
  const lines = diff.length ? diff.split("\n") : [];

  if (lines.length === 0) {
    return (
      <p className="rounded-lg border border-border bg-muted/30 px-4 py-6 text-center text-sm text-muted-foreground">
        No differences — the draft matches the current documentation.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-muted/20 font-mono text-xs leading-relaxed">
      {lines.map((line, i) => {
        const kind = classify(line);
        return (
          <div
            key={i}
            className={cn(
              "whitespace-pre px-4 py-0.5",
              kind === "add" && "bg-success/10 text-success",
              kind === "remove" && "bg-destructive/10 text-destructive",
              kind === "meta" && "bg-primary/10 text-primary",
              kind === "hunk" && "bg-muted/60 text-muted-foreground",
            )}
          >
            {line || " "}
          </div>
        );
      })}
    </div>
  );
}

function classify(line: string): "add" | "remove" | "meta" | "hunk" | "ctx" {
  if (line.startsWith("+++") || line.startsWith("---")) return "meta";
  if (line.startsWith("@@")) return "hunk";
  if (line.startsWith("+")) return "add";
  if (line.startsWith("-")) return "remove";
  return "ctx";
}
