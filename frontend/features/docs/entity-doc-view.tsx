"use client";

import { BookOpen, Code2, Download, FileText, Hash } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CodeBlock } from "@/components/shared/code-block";
import { EmptyState } from "@/components/shared/states";
import { KindIcon } from "@/components/shared/kind-icon";
import { Markdown } from "@/components/shared/markdown";
import { useDoc, useEntity } from "@/hooks/use-docengine";
import { API_URL } from "@/lib/api";
import type { EntityRead } from "@/types";

/**
 * The detailed documentation + source view for a single entity, used as the
 * main panel of the docs explorer (the "File/Function Documentation View").
 */
export function EntityDocView({ entity }: { entity: EntityRead }) {
  const detail = useEntity(entity.id);
  const doc = useDoc(entity.id);

  return (
    <div>
      {/* Header */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <KindIcon kind={entity.kind} className="h-5 w-5" />
        <h2 className="font-mono text-lg font-semibold">{entity.name}</h2>
        <Badge variant="outline">{entity.kind}</Badge>
        {entity.is_async && <Badge variant="secondary">async</Badge>}
      </div>
      <p className="mb-4 break-all font-mono text-xs text-muted-foreground">
        {entity.qualified_name} · {entity.relative_path}
        {entity.line_start ? `:${entity.line_start}` : ""}
      </p>

      {detail.data?.signature && (
        <CodeBlock code={detail.data.signature} className="mb-6" />
      )}

      <Tabs defaultValue="docs">
        <TabsList>
          <TabsTrigger value="docs">
            <BookOpen className="h-3.5 w-3.5" /> Documentation
          </TabsTrigger>
          <TabsTrigger value="source">
            <Code2 className="h-3.5 w-3.5" /> Source
          </TabsTrigger>
          <TabsTrigger value="details">
            <Hash className="h-3.5 w-3.5" /> Details
          </TabsTrigger>
        </TabsList>

        <TabsContent value="docs">
          {doc.isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-5 w-1/3" />
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-32 w-full" />
            </div>
          ) : doc.isError || !doc.data ? (
            <EmptyState
              icon={FileText}
              title="No documentation yet"
              description="Run “Generate docs” on this repository to create documentation for this entity."
            />
          ) : (
            <Card>
              <CardContent className="p-6">
                <div className="mb-3 flex items-center gap-2">
                  <Badge variant={doc.data.generator === "ai" ? "default" : "muted"}>
                    {doc.data.generator === "ai" ? "AI-generated" : "Fallback"}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    v{doc.data.version}
                  </span>
                  <Button asChild variant="ghost" size="sm" className="ml-auto">
                    <a href={`${API_URL}/docs/${entity.id}/export`}>
                      <Download className="h-3.5 w-3.5" /> Download .md
                    </a>
                  </Button>
                </div>
                <Markdown content={doc.data.content_markdown} />
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="source">
          {detail.data ? (
            <CodeBlock code={detail.data.source_code || "# source unavailable"} />
          ) : (
            <Skeleton className="h-48 w-full" />
          )}
        </TabsContent>

        <TabsContent value="details">
          {detail.data ? (
            <Card>
              <CardContent className="space-y-4 p-6 text-sm">
                <DetailRow label="Return type" value={detail.data.return_type ?? "—"} mono />
                {detail.data.parameters.length > 0 && (
                  <div>
                    <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      Parameters
                    </p>
                    <div className="space-y-1.5">
                      {detail.data.parameters.map((p) => (
                        <div
                          key={p.name}
                          className="flex flex-wrap items-center gap-2 font-mono text-xs"
                        >
                          <span className="text-foreground">{p.name}</span>
                          {p.annotation && (
                            <span className="text-primary">: {p.annotation}</span>
                          )}
                          {p.default && (
                            <span className="text-muted-foreground">
                              = {p.default}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {detail.data.decorators.length > 0 && (
                  <DetailRow
                    label="Decorators"
                    value={detail.data.decorators.map((d) => `@${d}`).join(", ")}
                    mono
                  />
                )}
                {detail.data.docstring && (
                  <div>
                    <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      Original docstring
                    </p>
                    <pre className="whitespace-pre-wrap rounded-lg bg-muted/50 p-3 font-mono text-xs">
                      {detail.data.docstring}
                    </pre>
                  </div>
                )}
              </CardContent>
            </Card>
          ) : (
            <Skeleton className="h-48 w-full" />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function DetailRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex flex-wrap items-baseline gap-2">
      <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <span className={mono ? "font-mono text-xs" : "text-sm"}>{value}</span>
    </div>
  );
}
