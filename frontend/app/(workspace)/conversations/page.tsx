"use client";
import Link from "next/link";
import { useState } from "react";
import { Pencil, Trash2, Plus, Search, MessagesSquare } from "lucide-react";
import { api } from "@/lib/api";
import type { Conversation } from "@/lib/api-types";
import { useResource, ErrorNotice, Empty } from "@/components/workspace";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogAction,
  AlertDialogCancel,
} from "@/components/ui/alert-dialog";
export default function Conversations() {
  const { data, error, loading, refresh } = useResource(api.conversations);
  const [query, setQuery] = useState("");
  const [renaming, setRenaming] = useState<Conversation | null>(null);
  const [deleting, setDeleting] = useState<Conversation | null>(null);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<Error | null>(null);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!renaming || !title.trim()) return;
    setBusy(true);
    setActionError(null);
    try {
      await api.renameConversation(
        renaming.conversation_id,
        title.trim().slice(0, 200),
      );
      await refresh();
      window.dispatchEvent(new Event("rag:conversations-changed"));
      setRenaming(null);
    } catch (e) {
      setActionError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!deleting) return;
    setBusy(true);
    setActionError(null);
    try {
      await api.deleteConversation(deleting.conversation_id);
      await refresh();
      window.dispatchEvent(new Event("rag:conversations-changed"));
      setDeleting(null);
    } catch (e) {
      setActionError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  const shown = data?.filter((c) =>
    (c.title ?? "").toLocaleLowerCase().includes(query.toLocaleLowerCase()),
  );
  return (
    <>
      <div className="row justify-between gap-4">
        <div>
          <h1>Conversations</h1>
          <p className="mt-2 text-sm muted">
            Pick up a thought, or start a new one.
          </p>
        </div>
        <Button asChild>
          <Link href="/chat">
            <Plus />
            New chat
          </Link>
        </Button>
      </div>
      <ErrorNotice error={error} />
      <div className="relative max-w-lg">
        <Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" />
        <label htmlFor="conversation-search" className="sr-only">
          Search conversation titles
        </label>
        <Input
          id="conversation-search"
          type="search"
          className="pl-10"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search conversations"
        />
      </div>
      {loading ? (
        <div
          role="status"
          aria-label="Loading conversations"
          className="space-y-3"
        >
          {[0, 1, 2].map((n) => (
            <Skeleton key={n} className="h-20 w-full" />
          ))}
        </div>
      ) : !shown?.length ? (
        <Empty>
          {query
            ? "No conversations match your search."
            : "Your conversations will appear here."}
        </Empty>
      ) : (
        <ul className="divide-y divide-border/50 rounded-xl border border-border/60">
          {shown.map((c) => (
            <li
              key={c.conversation_id}
              className="flex min-w-0 items-center justify-between gap-3 p-4 sm:p-5"
            >
              <div className="flex min-w-0 gap-3">
                <MessagesSquare className="mt-1 hidden size-4 shrink-0 text-muted-foreground sm:block" />
                <div className="min-w-0">
                  <Link
                    href={`/chat?conversation=${encodeURIComponent(c.conversation_id)}`}
                    className="break-words text-sm font-medium hover:underline underline-offset-4"
                  >
                    {c.title || "Untitled conversation"}
                  </Link>
                  <p className="mt-1 text-xs muted">
                    {c.message_count} messages
                  </p>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Rename ${c.title}`}
                  onClick={() => {
                    setActionError(null);
                    setRenaming(c);
                    setTitle(c.title ?? "");
                  }}
                >
                  <Pencil />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Delete ${c.title}`}
                  onClick={() => {
                    setActionError(null);
                    setDeleting(c);
                  }}
                >
                  <Trash2 />
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <Dialog
        open={!!renaming}
        onOpenChange={(open) => {
          if (!open && !busy) {
            setRenaming(null);
            setActionError(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename conversation</DialogTitle>
            <DialogDescription>
              Choose a title that helps you find this conversation.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={save} className="space">
            <div className="field">
              <label htmlFor="rename-title">Conversation title</label>
              <Input
                id="rename-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={200}
                required
                autoFocus
              />
            </div>
            <ErrorNotice error={actionError} />
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                disabled={busy}
                onClick={() => setRenaming(null)}
              >
                Cancel
              </Button>
              <Button disabled={busy || !title.trim()} type="submit">
                {busy ? "Saving…" : "Save title"}
              </Button>
            </DialogFooter>
          </form>
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
            <AlertDialogTitle>Delete conversation?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently deletes “{deleting?.title}”, its messages and
              saved memories. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
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
              {busy ? "Deleting…" : "Delete conversation"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
