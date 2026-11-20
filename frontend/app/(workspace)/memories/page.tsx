"use client";
import Link from "next/link";
import { useCallback, useState } from "react";
import {
  Brain,
  Search,
  Trash2,
  Link as LinkIcon,
  ArrowUpRight,
} from "lucide-react";
import { api, request } from "@/lib/api";
import type { Memory } from "@/lib/api-types";
import { useResource, ErrorNotice, Empty } from "@/components/workspace";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
  AlertDialogAction,
} from "@/components/ui/alert-dialog";
type MemorySource = {
  message_id: number;
  role: string | null;
  link_kind: string | null;
};
function SourceDetails({
  conversationId,
  memory,
}: {
  conversationId: string;
  memory: Memory;
}) {
  const load = useCallback(
    () =>
      request<MemorySource[]>(
        `conversations/${encodeURIComponent(conversationId)}/memories/${memory.memory_id}/sources`,
      ),
    [conversationId, memory.memory_id],
  );
  const { data, error, loading } = useResource(load);
  return (
    <>
      <ErrorNotice error={error} />
      {loading ? (
        <p role="status" className="text-sm muted">
          Loading source details…
        </p>
      ) : (
        <>
          <dl className="space-y-4 text-sm">
            <div>
              <dt className="text-xs muted">Provenance</dt>
              <dd className="mt-1">
                {memory.provenance === "USER_SUPPORTED"
                  ? "Supported by your messages"
                  : memory.provenance}
              </dd>
            </div>
            <div>
              <dt className="text-xs muted">Saved information</dt>
              <dd className="mt-1 break-words">{memory.memory}</dd>
            </div>
          </dl>
          {data?.length ? (
            <ul className="divide-y divide-border/50 rounded-xl border">
              {data.map((source, index) => (
                <li
                  key={`${source.message_id}-${index}`}
                  className="flex items-center justify-between gap-3 p-3 text-sm"
                >
                  <span>Message {source.message_id}</span>
                  <div className="flex flex-wrap justify-end gap-2">
                    <Badge>{source.role ?? "Unavailable"}</Badge>
                    {source.link_kind && (
                      <Badge>
                        {source.link_kind.replaceAll("_", " ").toLowerCase()}
                      </Badge>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm muted">
              No source links are currently available.
            </p>
          )}
          <Button asChild variant="outline">
            <Link
              href={`/chat?conversation=${encodeURIComponent(conversationId)}`}
            >
              Open conversation
              <ArrowUpRight />
            </Link>
          </Button>
        </>
      )}
    </>
  );
}
function MemoryItems({
  conversationId,
  query,
}: {
  conversationId: string;
  query: string;
}) {
  const load = useCallback(
    () => api.memories(conversationId),
    [conversationId],
  );
  const { data, error, loading, refresh } = useResource(load);
  const [deleting, setDeleting] = useState<Memory | null>(null),
    [source, setSource] = useState<Memory | null>(null);
  const [busy, setBusy] = useState(false),
    [actionError, setActionError] = useState<Error | null>(null);
  const shown = data?.memories.filter((m) =>
    `${m.memory} ${m.category}`
      .toLocaleLowerCase()
      .includes(query.toLocaleLowerCase()),
  );
  async function remove() {
    if (!deleting) return;
    setBusy(true);
    setActionError(null);
    try {
      await api.deleteMemory(conversationId, deleting.memory_id);
      await refresh();
      setDeleting(null);
    } catch (e) {
      setActionError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <ErrorNotice error={error} />
      {loading ? (
        <div role="status" aria-label="Loading memories" className="space-y-3">
          {[0, 1, 2].map((n) => (
            <Skeleton key={n} className="h-32" />
          ))}
        </div>
      ) : !shown?.length ? (
        <Empty>
          {query
            ? "No saved memories match your search."
            : "No supported memories in this conversation."}
        </Empty>
      ) : (
        <ul className="divide-y divide-border/50 rounded-xl border border-border/60">
          {shown.map((memory) => (
            <li key={memory.memory_id} className="space-y-4 p-4 sm:p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge className="capitalize">
                    {memory.category.replaceAll("_", " ")}
                  </Badge>
                  <span className="text-xs muted">
                    Supported by your messages
                  </span>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Delete memory ${memory.memory_id}`}
                  onClick={() => {
                    setActionError(null);
                    setDeleting(memory);
                  }}
                >
                  <Trash2 />
                </Button>
              </div>
              <p className="break-words text-sm leading-7">{memory.memory}</p>
              <Button
                variant="ghost"
                size="sm"
                className="-ml-2 text-muted-foreground"
                onClick={() => setSource(memory)}
                aria-label={`View sources for memory ${memory.memory_id}`}
              >
                <LinkIcon />
                View {memory.source_message_ids.length} source
                {memory.source_message_ids.length === 1 ? "" : "s"}
              </Button>
            </li>
          ))}
        </ul>
      )}
      {!!data?.unverified_hidden && (
        <p className="text-xs muted">
          {data.unverified_hidden} unsupported records are hidden.
        </p>
      )}
      <Dialog
        open={!!source}
        onOpenChange={(open) => {
          if (!open) setSource(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Memory sources</DialogTitle>
            <DialogDescription>
              Source links explain why this information was saved. Only your
              conversation is accessible.
            </DialogDescription>
          </DialogHeader>
          {source && (
            <SourceDetails
              key={source.memory_id}
              conversationId={conversationId}
              memory={source}
            />
          )}
        </DialogContent>
      </Dialog>
      <AlertDialog
        open={!!deleting}
        onOpenChange={(open) => {
          if (!open && !busy) {
            setDeleting(null);
            setActionError(null);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete and forget this memory?</AlertDialogTitle>
            <AlertDialogDescription>
              The saved memory will be deleted and its supporting messages
              excluded from future answer context. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <p className="rounded-lg bg-muted p-3 text-sm break-words">
            {deleting?.memory}
          </p>
          <ErrorNotice error={actionError} />
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={busy}
              onClick={(event) => {
                event.preventDefault();
                void remove();
              }}
            >
              {busy ? "Forgetting…" : "Delete and forget"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
export default function Memories() {
  const { data, error, loading } = useResource(api.conversations);
  const [id, setId] = useState(""),
    [query, setQuery] = useState("");
  return (
    <>
      <div>
        <div className="flex items-center gap-3">
          <Brain className="size-5 text-muted-foreground" />
          <h1>Memory</h1>
        </div>
        <p className="mt-2 text-sm muted">
          Information you have shared, with the sources that support it.
        </p>
      </div>
      <ErrorNotice error={error} />
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="field">
          <label htmlFor="memory-conversation">Conversation</label>
          <select
            id="memory-conversation"
            value={id}
            disabled={loading}
            onChange={(event) => {
              setId(event.target.value);
              setQuery("");
            }}
          >
            <option value="">Choose a conversation</option>
            {data?.map((c) => (
              <option key={c.conversation_id} value={c.conversation_id}>
                {c.title || "Untitled conversation"}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="memory-search">Search saved memories</label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" />
            <Input
              id="memory-search"
              className="pl-10"
              type="search"
              placeholder="Search this conversation’s memories"
              value={query}
              disabled={!id}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
        </div>
      </div>
      {id ? (
        <MemoryItems key={id} conversationId={id} query={query} />
      ) : (
        <Empty>
          Select a conversation to view its memories and source links.
        </Empty>
      )}
      <p className="text-xs muted">
        To manage a whole conversation and its saved memories, visit{" "}
        <Link href="/conversations" className="underline underline-offset-4">
          Conversations
        </Link>
        .
      </p>
    </>
  );
}
