"use client";

import { CheckCircle2, Cpu, Database, Server, XCircle } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { PageHeader } from "@/components/shared/page-header";
import { useConfig } from "@/hooks/use-docengine";
import { API_URL } from "@/lib/api";

export default function SettingsPage() {
  const config = useConfig();

  return (
    <>
      <PageHeader
        title="Settings"
        description="Connection and AI provider configuration for the documentation engine."
      />

      <div className="grid gap-6 lg:grid-cols-2">
        {/* AI provider */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Cpu className="h-4 w-4 text-muted-foreground" /> AI Provider
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            {config.isLoading ? (
              <Skeleton className="h-24 w-full" />
            ) : config.isError ? (
              <p className="text-destructive">
                Could not reach the backend. Is it running at {API_URL}?
              </p>
            ) : (
              <>
                <Row label="OpenRouter">
                  {config.data!.ai_enabled ? (
                    <Badge variant="success">
                      <CheckCircle2 className="h-3 w-3" /> Connected
                    </Badge>
                  ) : (
                    <Badge variant="warning">
                      <XCircle className="h-3 w-3" /> Not configured
                    </Badge>
                  )}
                </Row>
                <Separator />
                <Row label="Model">
                  <span className="font-mono text-xs">{config.data!.model}</span>
                </Row>
                <Separator />
                <Row label="Embeddings">
                  <Badge variant="muted">{config.data!.embedding_mode}</Badge>
                </Row>
                {!config.data!.ai_enabled && (
                  <p className="rounded-lg bg-muted/50 p-3 text-xs text-muted-foreground">
                    Set <code className="font-mono">OPENROUTER_API_KEY</code> in the
                    backend <code className="font-mono">.env</code> to enable
                    AI-generated docs and chat. The engine still works with a
                    deterministic local fallback.
                  </p>
                )}
              </>
            )}
          </CardContent>
        </Card>

        {/* Connection */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Server className="h-4 w-4 text-muted-foreground" /> Connection
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <Row label="API endpoint">
              <span className="break-all font-mono text-xs">{API_URL}</span>
            </Row>
            <Separator />
            <Row label="Health">
              {config.isError ? (
                <Badge variant="destructive">
                  <XCircle className="h-3 w-3" /> Offline
                </Badge>
              ) : (
                <Badge variant="success">
                  <CheckCircle2 className="h-3 w-3" /> Online
                </Badge>
              )}
            </Row>
          </CardContent>
        </Card>

        {/* Stack */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Database className="h-4 w-4 text-muted-foreground" /> Stack
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["Frontend", "Next.js · TypeScript · Tailwind · shadcn/ui"],
              ["Backend", "FastAPI · SQLAlchemy · SQLite"],
              ["AI", "OpenRouter (configurable model)"],
              ["RAG", "ChromaDB · chunking + embeddings"],
            ].map(([k, v]) => (
              <div key={k} className="rounded-lg border border-border p-3">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {k}
                </p>
                <p className="mt-1 text-xs">{v}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      {children}
    </div>
  );
}
