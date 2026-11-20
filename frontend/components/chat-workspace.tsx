"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ArrowUp,
  BookOpen,
  Check,
  ChevronDown,
  FileText,
  LoaderCircle,
  Paperclip,
  Plus,
  RotateCcw,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import { reconcileChat } from "@/lib/chat-reconciliation";
import { api, fileUrl } from "@/lib/api";
import type { Message, Citation, Document } from "@/lib/api-types";
import { useResource, ErrorNotice } from "@/components/workspace";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ChatMarkdown, CopyText } from "@/components/chat-markdown";

type PendingTurn = { turn_id: string; message: string };
type Attachment = { id: string; name: string; status: string };

function pendingTurn(conversationId: string): PendingTurn | null {
  const value = sessionStorage.getItem(`rag-turn:${conversationId}`);
  if (!value) return null;
  const parsed: unknown = JSON.parse(value);
  if (
    parsed &&
    typeof parsed === "object" &&
    "turn_id" in parsed &&
    "message" in parsed &&
    typeof parsed.turn_id === "string" &&
    /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(parsed.turn_id) &&
    typeof parsed.message === "string" &&
    parsed.message.trim()
  )
    return parsed as PendingTurn;
  throw new Error(
    "The pending question could not be loaded. Reopen this conversation to check for a saved answer.",
  );
}

function answerStatus(message: Message) {
  const value =
    message.answer_metadata?.answer_status ?? message.answer_metadata?.status;
  if (!value) return null;
  if (["error", "failed", "unverified"].includes(value))
    return { label: "failed", className: "status-failed" };
  if (value === "conflict")
    return { label: "conflicting evidence", className: "status-partial" };
  return { label: value, className: `status-${value}` };
}

function CitationLink({
  citation,
  documents,
}: {
  citation: Citation;
  documents: Document[];
}) {
  const doc = documents.find((item) =>
    citation.document_id
      ? item.id === citation.document_id
      : item.id === citation.document,
  );
  const label = `${citation.ref ?? "Source"} · ${doc?.filename ?? citation.document ?? "Document"}${citation.page ? ` · p. ${citation.page}` : ""}`;
  const style =
    "inline-flex max-w-full items-center gap-1.5 rounded-full border bg-card px-3 py-1.5 text-xs text-muted-foreground transition-colors";
  return doc ? (
    <a
      href={fileUrl(doc.id, citation.page ?? 1)}
      target="_blank"
      rel="noopener noreferrer"
      className={`${style} hover:bg-accent hover:text-foreground`}
      aria-label={`Open citation ${label}`}
    >
      <FileText className="size-3.5 shrink-0" aria-hidden />
      <span className="truncate">{label}</span>
    </a>
  ) : (
    <span className={style}>
      <FileText className="size-3.5 shrink-0" aria-hidden />
      <span className="truncate">{label}</span>
    </span>
  );
}

export function ChatWorkspace({ initialId }: { initialId?: string }) {
  const [id, setId] = useState(initialId ?? "");
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [recovering, setRecovering] = useState(false);
  const [pending, setPending] = useState<PendingTurn | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [historyLoading, setHistoryLoading] = useState(Boolean(initialId));
  const [uploading, setUploading] = useState(false);
  const [attachment, setAttachment] = useState<Attachment | null>(null);
  const [uploadError, setUploadError] = useState<Error | null>(null);
  const docs = useResource(api.documents);
  const refreshDocuments = docs.refresh;
  const bottom = useRef<HTMLDivElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const sending = useRef(false);
  const processing = Boolean(
    attachment && ["queued", "running"].includes(attachment.status),
  );

  useEffect(() => {
    if (!initialId) return;
    let active = true;
    api
      .conversation(initialId)
      .then(async (data) => {
        if (active) {
          setMessages(data.messages);
          setHistoryLoading(false);
        }
        const stored = pendingTurn(initialId);
        if (!stored) return;
        if (active) {
          setBusy(true);
          setRecovering(true);
          setPending(stored);
          setText(stored.message);
        }
        try {
          await reconcileChat(null, () => api.turn(initialId, stored.turn_id));
          const current = await api.conversation(initialId);
          sessionStorage.removeItem(`rag-turn:${initialId}`);
          if (active) {
            setMessages(current.messages);
            setPending(null);
            setText("");
          }
        } finally {
          if (active) {
            setBusy(false);
            setRecovering(false);
          }
        }
      })
      .catch((caught) => {
        if (active) setError(caught as Error);
      })
      .finally(() => {
        if (active) setHistoryLoading(false);
      });
    return () => {
      active = false;
    };
  }, [initialId]);

  useEffect(() => {
    if (textarea.current) {
      textarea.current.style.height = "auto";
      textarea.current.style.height = `${Math.min(textarea.current.scrollHeight, 180)}px`;
    }
  }, [text]);

  useEffect(() => {
    bottom.current?.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
      block: "nearest",
    });
  }, [messages, busy]);

  useEffect(() => {
    if (!attachment || !["queued", "running"].includes(attachment.status))
      return;
    let active = true;
    const timer = window.setInterval(() => {
      if (document.hidden) return;
      api
        .document(attachment.id)
        .then((document) => {
          if (!active) return;
          setAttachment({
            id: document.id,
            name: document.filename,
            status: document.status,
          });
          if (document.status === "ready") void refreshDocuments();
        })
        .catch((caught) => {
          if (active) setUploadError(caught as Error);
        });
    }, 2500);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [attachment, refreshDocuments]);

  async function upload(file?: File) {
    if (!file || uploading || busy) return;
    setUploadError(null);
    if (
      !file.name.toLowerCase().endsWith(".pdf") ||
      (file.type && file.type !== "application/pdf") ||
      !file.size ||
      file.size > 25 * 1024 * 1024
    ) {
      setUploadError(new Error("Choose a non-empty PDF of 25 MB or less."));
      if (fileInput.current) fileInput.current.value = "";
      return;
    }
    setUploading(true);
    try {
      const result = await api.upload(file);
      setAttachment({
        id: result.document_id,
        name: result.filename,
        status: result.status,
      });
      await refreshDocuments();
    } catch (caught) {
      setUploadError(caught as Error);
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function sendMessage(message: string) {
    if (!message.trim() || sending.current || busy || uploading || processing)
      return;
    sending.current = true;
    setBusy(true);
    setError(null);
    let conversationId = id;
    try {
      if (!conversationId) {
        const conversation = await api.createConversation(
          message.slice(0, 100),
        );
        conversationId = conversation.conversation_id;
        setId(conversationId);
        window.dispatchEvent(new Event("rag:conversations-changed"));
      }
      window.history.replaceState(
        null,
        "",
        `/chat?conversation=${encodeURIComponent(conversationId)}`,
      );
      const key = `rag-turn:${conversationId}`;
      const previous = pendingTurn(conversationId);
      if (previous && previous.message !== message)
        throw new Error(
          "Check the unconfirmed question before sending a different one.",
        );
      const turn = previous ?? { turn_id: crypto.randomUUID(), message };
      sessionStorage.setItem(key, JSON.stringify(turn));
      setPending(turn);
      setRecovering(Boolean(previous));
      const response = await reconcileChat(
        () => api.chat(conversationId, message, turn.turn_id),
        () => api.turn(conversationId, turn.turn_id),
      );
      const current = await api.conversation(conversationId);
      // Deletion cleanup deliberately excludes these messages from future context.
      // Its authoritative live acknowledgement remains visible without inventing history.
      if (response.kind === "memory_deletion") {
        const last = current.messages.at(-1);
        const previous = current.messages.at(-2);
        if (
          last?.role === "assistant" &&
          last.content === response.answer &&
          previous?.content === message
        ) {
          setMessages(
            current.messages.map((item) =>
              item.id === last.id
                ? { ...item, answer_metadata: response }
                : item,
            ),
          );
        } else {
          const userId = Date.now();
          setMessages([
            ...current.messages,
            { id: userId, role: "user", content: message },
            {
              id: userId + 1,
              role: "assistant",
              content: response.answer,
              answer_metadata: response,
            },
          ]);
        }
      } else {
        setMessages(current.messages);
      }
      sessionStorage.removeItem(key);
      setPending(null);
      setText("");
      window.dispatchEvent(new Event("rag:conversations-changed"));
    } catch (caught) {
      setError(caught as Error);
    } finally {
      sending.current = false;
      setBusy(false);
      setRecovering(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void sendMessage(text.trim());
  }
  function fresh() {
    setId("");
    setMessages([]);
    setError(null);
    setPending(null);
    setText("");
    window.history.replaceState(null, "", "/chat");
    window.dispatchEvent(new Event("rag:conversations-changed"));
    textarea.current?.focus();
  }
  function askAbout(document: Document) {
    setText(`In ${document.filename}, `);
    textarea.current?.focus();
  }
  const showPendingQuestion =
    busy && pending && messages.at(-1)?.content !== pending.message;

  return (
    <section
      className="mx-auto flex h-full min-h-0 w-full max-w-[54rem] flex-1 flex-col"
      aria-label="Chat workspace"
    >
      <div className="flex shrink-0 items-center justify-between gap-3 py-4 sm:py-5">
        <div className="min-w-0">
          <h1 className="text-base font-medium tracking-normal sm:text-lg">
            Chat workspace
          </h1>
          <p className="mt-0.5 hidden text-xs text-muted-foreground sm:block">
            Your documents. Clear answers. Original sources.
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={fresh}
          disabled={busy}
          className="shrink-0 rounded-lg text-muted-foreground"
        >
          <Plus aria-hidden /> New chat
        </Button>
      </div>
      <div className="shrink-0 space-y-2 [&:not(:empty)]:pb-3">
        <ErrorNotice error={error || docs.error || uploadError} />
        {error && pending && !busy && (
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Button
              size="sm"
              variant="outline"
              onClick={() => void sendMessage(pending.message)}
            >
              <RotateCcw aria-hidden /> Retry safely
            </Button>
            <span>Checks the same question for a saved answer.</span>
          </div>
        )}
      </div>
      <div
        className="relative min-h-0 flex-1 overflow-y-auto overscroll-contain px-1 pb-5 sm:px-2"
        role="log"
        aria-label="Conversation messages"
        tabIndex={0}
        aria-live="polite"
        aria-busy={busy || historyLoading}
      >
        {historyLoading ? (
          <div
            className="flex items-center gap-2 py-10 text-sm text-muted-foreground"
            role="status"
          >
            <LoaderCircle className="size-4 animate-spin" aria-hidden />
            Loading conversation…
          </div>
        ) : !messages.length && !busy ? (
          <div className="flex min-h-full flex-col items-center justify-center px-2 pb-8 text-center sm:pb-16">
            <div className="mb-6 rounded-2xl border bg-card p-3">
              <BookOpen className="size-6" strokeWidth={1.5} aria-hidden />
            </div>
            <h2 className="max-w-md text-2xl font-medium tracking-tight sm:text-3xl">
              What would you like to explore?
            </h2>
            <p className="mt-3 max-w-sm text-sm leading-6 text-muted-foreground">
              Ask about your files. Follow each citation back to the original
              page.
            </p>
            <div className="mt-7 flex max-w-md flex-wrap justify-center gap-2">
              {[
                {
                  label: "Summarize a document",
                  text: "Summarize the main points in ",
                  icon: FileText,
                },
                {
                  label: "Find a detail",
                  text: "What does the document say about ",
                  icon: Search,
                },
                {
                  label: "Compare information",
                  text: "Compare ",
                  icon: Sparkles,
                },
              ].map(({ label, text, icon: Icon }) => (
                <Button
                  key={label}
                  variant="outline"
                  size="sm"
                  className="rounded-full border-border/60 bg-transparent text-xs text-muted-foreground"
                  onClick={() => {
                    setText(text);
                    textarea.current?.focus();
                  }}
                >
                  <Icon className="size-3.5" aria-hidden />
                  {label}
                </Button>
              ))}
            </div>
            {!docs.loading && !docs.data?.length && (
              <Link
                href="/documents"
                className="mt-6 text-sm underline underline-offset-4"
              >
                Add your first source
              </Link>
            )}
          </div>
        ) : (
          <div className="space-y-8 py-3 sm:space-y-10">
            {messages.map((message) => {
              const status = answerStatus(message);
              const citations = message.answer_metadata?.citations ?? [];
              return (
                <article
                  key={message.id}
                  className={
                    message.role === "user"
                      ? "ml-auto max-w-[90%] rounded-3xl bg-secondary px-5 py-3 sm:max-w-[82%]"
                      : "min-w-0 pr-1"
                  }
                >
                  <div
                    className={`mb-2 flex items-center gap-2 ${message.role === "user" ? "sr-only" : ""}`}
                  >
                    <h2 className="text-sm font-medium">
                      {message.role === "user" ? "You" : "RAG"}
                    </h2>
                    {status && (
                      <Badge
                        className={`${status.className} border-0 px-2 py-0.5 text-[10px] font-normal`}
                      >
                        {status.label}
                      </Badge>
                    )}
                  </div>
                  {message.role === "user" ? (
                    <p className="whitespace-pre-wrap break-words text-[15px] leading-7 [overflow-wrap:anywhere]">
                      {message.content}
                    </p>
                  ) : (
                    <ChatMarkdown content={message.content} />
                  )}
                  {Boolean(citations.length) && (
                    <div className="mt-4 flex flex-wrap gap-2">
                      {citations.map((citation, index) => (
                        <CitationLink
                          key={`${citation.ref}-${index}`}
                          citation={citation}
                          documents={docs.data ?? []}
                        />
                      ))}
                    </div>
                  )}
                  {message.role === "assistant" && (
                    <div className="mt-2 flex items-center gap-1">
                      <CopyText text={message.content} />
                    </div>
                  )}
                </article>
              );
            })}
            {showPendingQuestion && (
              <article className="ml-auto max-w-[90%] rounded-3xl bg-secondary px-5 py-3 sm:max-w-[82%]">
                <h2 className="sr-only">You</h2>
                <p className="whitespace-pre-wrap break-words text-[15px] leading-7 [overflow-wrap:anywhere]">
                  {pending.message}
                </p>
              </article>
            )}
            {busy && (
              <div
                role="status"
                className="flex items-center gap-3 py-2 text-sm text-muted-foreground"
              >
                <LoaderCircle className="size-4 animate-spin" aria-hidden />
                <span>
                  {recovering
                    ? "Checking for a saved answer…"
                    : "Searching your sources and preparing an answer…"}
                </span>
              </div>
            )}
          </div>
        )}
        <div ref={bottom} />
      </div>
      <div className="z-10 shrink-0 bg-background pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3">
        <form
          onSubmit={submit}
          className="rounded-3xl border border-border/60 bg-composer p-3 shadow-sm sm:p-4"
        >
          {attachment && (
            <div className="mb-3 flex min-w-0 items-center gap-2 rounded-xl border border-border/60 bg-background/40 px-3 py-2 text-xs">
              <FileText className="size-4 shrink-0" aria-hidden />
              <span className="min-w-0 flex-1 truncate">{attachment.name}</span>
              <span
                role="status"
                className="inline-flex shrink-0 items-center gap-1.5 text-muted-foreground"
              >
                {processing ? (
                  <LoaderCircle className="size-3 animate-spin" aria-hidden />
                ) : attachment.status === "ready" ? (
                  <Check className="size-3" aria-hidden />
                ) : null}
                {attachment.status === "ready"
                  ? "Ready"
                  : processing
                    ? "Processing"
                    : attachment.status}
              </span>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                className="size-6 shrink-0"
                onClick={() => setAttachment(null)}
                aria-label="Dismiss upload status"
              >
                <X aria-hidden />
              </Button>
            </div>
          )}
          <label className="sr-only" htmlFor="question">
            Your message
          </label>
          <textarea
            ref={textarea}
            id="question"
            name="question"
            rows={1}
            maxLength={8000}
            required
            placeholder="Ask anything about your documents"
            value={text}
            onChange={(event) => setText(event.target.value)}
            disabled={busy || historyLoading}
            onKeyDown={(event) => {
              if (
                event.key === "Enter" &&
                !event.shiftKey &&
                !event.nativeEvent.isComposing
              ) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            className="max-h-[180px] min-h-12 w-full resize-none border-0 bg-transparent px-1 py-2 text-[15px] leading-7 outline-none placeholder:text-muted-foreground focus-visible:outline-none disabled:opacity-60"
          />
          <div className="mt-2 flex items-center justify-between gap-2">
            <div className="flex min-w-0 items-center gap-1">
              <input
                ref={fileInput}
                type="file"
                accept="application/pdf,.pdf"
                className="sr-only"
                tabIndex={-1}
                aria-label="Choose chat PDF"
                onChange={(event) => void upload(event.target.files?.[0])}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-9 rounded-full text-muted-foreground"
                onClick={() => fileInput.current?.click()}
                disabled={busy || uploading}
                aria-label="Attach PDF"
                title="Upload PDF, up to 25 MB"
              >
                {uploading ? (
                  <LoaderCircle className="animate-spin" aria-hidden />
                ) : (
                  <Paperclip aria-hidden />
                )}
              </Button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="gap-1 rounded-full px-2.5 text-xs text-muted-foreground"
                    aria-label="Browse document sources"
                  >
                    <BookOpen className="size-3.5" aria-hidden />
                    <span>Sources</span>
                    <ChevronDown className="size-3" aria-hidden />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  align="start"
                  side="top"
                  className="max-h-80 w-[min(22rem,calc(100vw-2rem))] overflow-y-auto"
                >
                  <DropdownMenuLabel>Your document library</DropdownMenuLabel>
                  <p className="px-3 pb-2 text-xs leading-5 text-muted-foreground">
                    Questions search ready documents. Choose a unique filename
                    to ask about it.
                  </p>
                  {docs.loading ? (
                    <p
                      role="status"
                      className="px-3 py-2 text-xs text-muted-foreground"
                    >
                      Loading sources…
                    </p>
                  ) : !docs.data?.length ? (
                    <p className="px-3 py-2 text-xs text-muted-foreground">
                      No documents yet.
                    </p>
                  ) : (
                    docs.data.map((document) => {
                      const unique =
                        docs.data?.filter(
                          (item) => item.filename === document.filename,
                        ).length === 1;
                      return (
                        <div key={document.id} className="px-1">
                          <DropdownMenuItem
                            disabled={
                              busy || document.status !== "ready" || !unique
                            }
                            onSelect={() => askAbout(document)}
                            aria-label={`Ask about ${document.filename}`}
                          >
                            <FileText className="shrink-0" aria-hidden />
                            <span className="min-w-0 flex-1 truncate">
                              {document.filename}
                            </span>
                            <span className="shrink-0 text-[10px] text-muted-foreground">
                              {document.status}
                            </span>
                          </DropdownMenuItem>
                        </div>
                      );
                    })
                  )}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem asChild>
                    <Link href="/documents">
                      <BookOpen aria-hidden />
                      Open document library
                    </Link>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
            <Button
              type="submit"
              size="icon"
              className="size-9 shrink-0 rounded-full"
              disabled={
                busy ||
                uploading ||
                processing ||
                historyLoading ||
                !text.trim()
              }
              aria-label="Send"
              title="Send message (Enter)"
            >
              {busy ? (
                <LoaderCircle className="animate-spin" aria-hidden />
              ) : (
                <ArrowUp aria-hidden />
              )}
            </Button>
          </div>
        </form>
        <p className="mt-2 text-center text-[10px] leading-5 text-muted-foreground sm:text-[11px]">
          {uploading
            ? "Uploading PDF…"
            : processing
              ? "Your PDF is processing. You can ask about it when indexing finishes."
              : "RAG can make mistakes. Check the original sources."}
        </p>
      </div>
    </section>
  );
}
