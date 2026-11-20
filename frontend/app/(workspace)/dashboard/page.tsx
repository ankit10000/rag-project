"use client";
import Link from "next/link";
import {
  Files,
  MessagesSquare,
  Activity,
  ArrowUpRight,
  SquarePen,
  FilePlus2,
} from "lucide-react";
import { api } from "@/lib/api";
import { useResource, useUser, ErrorNotice } from "@/components/workspace";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export default function Dashboard() {
  const user = useUser();
  const docs = useResource(api.documents);
  const conversations = useResource(api.conversations);
  const jobs = useResource(api.jobs);
  return (
    <div className="mx-auto w-full max-w-4xl space-y-9 py-3 sm:py-8">
      <header className="space-y-3">
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
          Your knowledge workspace
        </p>
        <h1>Hello, {user?.display_name || "there"}.</h1>
        <p className="max-w-xl text-sm text-muted-foreground sm:text-base">
          A quiet place to work with your documents. Ask a question, follow the
          sources, and keep the context that matters.
        </p>
        <div className="flex flex-wrap gap-2 pt-3">
          <Button asChild>
            <Link href="/chat">
              <SquarePen />
              Start a conversation
            </Link>
          </Button>
          <Button variant="outline" asChild>
            <Link href="/documents">
              <FilePlus2 />
              Add a source
            </Link>
          </Button>
        </div>
      </header>
      <ErrorNotice error={docs.error || conversations.error || jobs.error} />
      <section
        aria-label="Workspace summary"
        className="grid grid-cols-1 divide-y divide-border/40 rounded-xl border border-border/40 bg-surface/40 sm:grid-cols-3 sm:divide-x sm:divide-y-0"
      >
        {[
          {
            name: "Documents",
            value: docs.data?.length,
            href: "/documents",
            icon: Files,
            loading: docs.loading,
          },
          {
            name: "Conversations",
            value: conversations.data?.length,
            href: "/conversations",
            icon: MessagesSquare,
            loading: conversations.loading,
          },
          {
            name: "Active jobs",
            value: jobs.data?.filter((job) =>
              ["queued", "running"].includes(job.status),
            ).length,
            href: "/jobs",
            icon: Activity,
            loading: jobs.loading,
          },
        ].map(({ name, value, href, icon: Icon, loading }) => (
          <Link
            href={href}
            key={name}
            className="flex items-center gap-3 px-5 py-5 transition-colors hover:bg-accent/30"
          >
            <Icon className="size-4 text-muted-foreground" />
            <span className="flex-1 text-sm text-muted-foreground">{name}</span>
            {loading ? (
              <Skeleton className="h-6 w-6" />
            ) : (
              <span className="text-lg font-medium tabular-nums">
                {value ?? "—"}
              </span>
            )}
          </Link>
        ))}
      </section>
      <section className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-medium">Pick up where you left off</h2>
          <Link
            href="/conversations"
            className="inline-flex items-center gap-1.5 rounded text-xs text-muted-foreground hover:text-foreground"
          >
            View all
            <ArrowUpRight className="size-3" />
          </Link>
        </div>
        {conversations.loading ? (
          <div className="space-y-3">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : conversations.data?.length ? (
          <div className="divide-y divide-border/30">
            {conversations.data.slice(0, 4).map((conversation) => (
              <Link
                href={`/chat?conversation=${encodeURIComponent(conversation.conversation_id)}`}
                key={conversation.conversation_id}
                className="flex min-w-0 items-center gap-3 rounded-lg px-3 py-4 text-sm hover:bg-accent/30"
              >
                <MessagesSquare className="size-4 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate">
                  {conversation.title}
                </span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {conversation.message_count} messages
                </span>
              </Link>
            ))}
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-border/50 p-7 text-sm text-muted-foreground">
            <p>Your first conversation starts with a question.</p>
            <p className="mt-1">
              Upload a PDF to get grounded answers with links to the original
              pages. Scanned pages use local OCR.
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
