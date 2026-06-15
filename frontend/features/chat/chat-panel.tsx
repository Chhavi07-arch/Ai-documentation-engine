"use client";

import * as React from "react";
import { Bot, CornerDownLeft, FileText, Loader2, Trash2, User } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Markdown } from "@/components/shared/markdown";
import { docengine } from "@/services/docengine";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { RetrievedSource } from "@/types";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: RetrievedSource[];
  grounded?: boolean;
}

/**
 * Documentation-aware chat. Answers are grounded in the selected repository's
 * docs and cite the sources that were retrieved.
 */
export function ChatPanel({ repositoryId }: { repositoryId: number }) {
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [input, setInput] = React.useState("");
  const [pending, setPending] = React.useState(false);
  const scrollRef = React.useRef<HTMLDivElement>(null);

  const storageKey = `docengine.chat.${repositoryId}`;

  // Load any saved conversation for this repository (survives navigation and
  // refresh within the session) whenever the selected repository changes.
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const saved = window.sessionStorage.getItem(storageKey);
      setMessages(saved ? (JSON.parse(saved) as ChatMessage[]) : []);
    } catch {
      setMessages([]);
    }
  }, [storageKey]);

  // Persist the conversation so switching sections doesn't lose it.
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.sessionStorage.setItem(storageKey, JSON.stringify(messages));
    } catch {
      // Ignore storage quota/serialization errors — chat still works in-memory.
    }
  }, [messages, storageKey]);

  React.useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, pending]);

  const send = async () => {
    const text = input.trim();
    if (!text || pending) return;

    setMessages((m) => [...m, { role: "user", content: text }]);
    setInput("");
    setPending(true);
    try {
      const res = await docengine.chat(repositoryId, text);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: res.answer,
          sources: res.sources,
          grounded: res.grounded,
        },
      ]);
    } catch (err) {
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content:
            err instanceof ApiError
              ? `⚠️ ${err.message}`
              : "⚠️ Something went wrong.",
        },
      ]);
    } finally {
      setPending(false);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const clear = () => setMessages([]);

  return (
    <div className="flex h-[calc(100vh-220px)] flex-col rounded-xl border border-border bg-card">
      {messages.length > 0 && (
        <div className="flex items-center justify-between border-b border-border px-4 py-2">
          <span className="text-xs text-muted-foreground">
            Grounded in this repository&apos;s documentation
          </span>
          <Button variant="ghost" size="sm" onClick={clear}>
            <Trash2 className="h-3.5 w-3.5" /> Clear
          </Button>
        </div>
      )}
      <div ref={scrollRef} className="flex-1 space-y-6 overflow-y-auto p-6">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="mb-4 rounded-full bg-primary/10 p-3">
              <Bot className="h-6 w-6 text-primary" />
            </div>
            <h3 className="text-sm font-semibold">Ask about this codebase</h3>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">
              Answers are grounded only in the generated documentation, with
              source references. Try “What does the auth service do?”
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={cn(
              "flex gap-3",
              msg.role === "user" ? "justify-end" : "justify-start",
            )}
          >
            {msg.role === "assistant" && (
              <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                <Bot className="h-4 w-4 text-primary" />
              </div>
            )}
            <div
              className={cn(
                "max-w-[80%] rounded-xl px-4 py-3 text-sm",
                msg.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted/60",
              )}
            >
              {msg.role === "assistant" ? (
                <Markdown content={msg.content} />
              ) : (
                msg.content
              )}

              {msg.sources && msg.sources.length > 0 && (
                <div className="mt-3 border-t border-border/60 pt-3">
                  <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    Sources
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {msg.sources.map((s, j) => (
                      <Badge key={j} variant="outline" className="font-mono text-[10px]">
                        <FileText className="h-3 w-3" />
                        {s.qualified_name}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
            {msg.role === "user" && (
              <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted">
                <User className="h-4 w-4" />
              </div>
            )}
          </div>
        ))}

        {pending && (
          <div className="flex gap-3">
            <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10">
              <Bot className="h-4 w-4 text-primary" />
            </div>
            <div className="flex items-center gap-2 rounded-xl bg-muted/60 px-4 py-3 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Searching docs…
            </div>
          </div>
        )}
      </div>

      <div className="border-t border-border p-4">
        <div className="relative">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask a question about the documentation…"
            className="min-h-[52px] resize-none pr-24"
          />
          <Button
            size="sm"
            onClick={send}
            disabled={!input.trim() || pending}
            className="absolute bottom-2 right-2"
          >
            Send <CornerDownLeft className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </div>
  );
}
