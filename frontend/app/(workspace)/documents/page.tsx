"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Upload,
  FileText,
  Trash2,
  RefreshCw,
  Search,
  MoreHorizontal,
  ExternalLink,
  Library,
  X,
  LoaderCircle,
} from "lucide-react";
import { api } from "@/lib/api";
import type { Document } from "@/lib/api-types";
import {
  pdfValidationError,
  processingSummary,
  boundedProgress,
} from "@/lib/document-ui";
import { useResource, ErrorNotice } from "@/components/workspace";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from "@/components/ui/table";
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
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { DocumentStatus } from "@/components/document-status";

export default function Documents() {
  const documents = useResource(api.documents);
  const jobs = useResource(api.jobs);
  const [actionError, setActionError] = useState<Error | null>(null);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Document | null>(null);
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const { refresh: refreshDocuments } = documents;
  const { refresh: refreshJobs } = jobs;
  const refresh = useCallback(async () => {
    await Promise.all([refreshDocuments(), refreshJobs()]);
  }, [refreshDocuments, refreshJobs]);
  const processing = documents.data?.some((doc) =>
    ["queued", "running"].includes(doc.status),
  );
  useEffect(() => {
    if (!processing) return;
    const timer = setInterval(() => {
      if (!document.hidden) void refresh();
    }, 5000);
    return () => clearInterval(timer);
  }, [processing, refresh]);
  async function upload(file?: File) {
    if (!file || uploading) return;
    setActionError(null);
    setNotice("");
    const invalid = pdfValidationError(file);
    if (invalid) {
      setActionError(new Error(invalid));
      if (input.current) input.current.value = "";
      return;
    }
    setUploading(true);
    try {
      await api.upload(file);
      setNotice(
        "Upload received. OCR and indexing will continue in the background.",
      );
      await refresh();
    } catch (error) {
      setActionError(error as Error);
    } finally {
      setUploading(false);
      if (input.current) input.current.value = "";
    }
  }
  async function remove() {
    if (!pendingDelete || deleting) return;
    setDeleting(true);
    setActionError(null);
    try {
      await api.deleteDocument(pendingDelete.id);
      setPendingDelete(null);
      setNotice("Document and its search index deleted.");
      await refresh();
    } catch (error) {
      setActionError(error as Error);
    } finally {
      setDeleting(false);
    }
  }
  const visible = (documents.data ?? []).filter(
    (doc) =>
      doc.filename.toLocaleLowerCase().includes(search.toLocaleLowerCase()) &&
      (filter === "all" ||
        (filter === "processing"
          ? ["queued", "running"].includes(doc.status)
          : doc.status === filter)),
  );
  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
            Your sources
          </p>
          <h1>Documents</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            A private library for grounded answers.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => void refresh()}
          disabled={documents.loading}
          aria-label="Refresh documents"
        >
          <RefreshCw
            className={
              documents.loading ? "animate-spin motion-reduce:animate-none" : ""
            }
          />
          Refresh
        </Button>
      </div>
      <ErrorNotice error={documents.error || actionError} />
      <section
        aria-label="Upload a PDF"
        className={`rounded-xl border border-dashed p-5 transition-colors sm:p-6 ${dragging ? "border-foreground bg-accent" : "border-border/70 bg-card/40"}`}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          if (!(
            event.relatedTarget instanceof Node &&
            event.currentTarget.contains(event.relatedTarget)
          ))
            setDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          if (event.dataTransfer.files.length > 1)
            setActionError(new Error("Upload one PDF at a time."));
          else void upload(event.dataTransfer.files[0]);
        }}
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-lg border bg-secondary">
              <Upload className="size-4" aria-hidden />
            </span>
            <div>
              <h2 className="text-sm font-medium">Add a source</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Drop a PDF here, or choose a file.
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Native and scanned pages · up to 25 MB per PDF
              </p>
            </div>
          </div>
          <div className="shrink-0">
            <label className="sr-only" htmlFor="pdf-upload">
              Choose PDF
            </label>
            <input
              ref={input}
              id="pdf-upload"
              type="file"
              accept="application/pdf,.pdf"
              disabled={uploading}
              className="sr-only"
              onChange={(event) => void upload(event.target.files?.[0])}
            />
            <Button onClick={() => input.current?.click()} disabled={uploading}>
              {uploading ? (
                <LoaderCircle className="animate-spin motion-reduce:animate-none" />
              ) : (
                <Upload />
              )}
              {uploading ? "Uploading…" : "Upload PDF"}
            </Button>
          </div>
        </div>
        {uploading && (
          <p role="status" className="mt-4 text-sm text-muted-foreground">
            Uploading your PDF…
          </p>
        )}
      </section>
      {notice && (
        <div
          role="status"
          className="flex items-start justify-between gap-3 rounded-lg border bg-secondary/50 px-4 py-3 text-sm"
        >
          <p>
            {notice}{" "}
            <Link href="/jobs" className="underline underline-offset-4">
              View activity
            </Link>
          </p>
          <Button
            variant="ghost"
            size="icon"
            className="size-6 shrink-0"
            aria-label="Dismiss document notice"
            onClick={() => setNotice("")}
          >
            <X />
          </Button>
        </div>
      )}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full sm:max-w-xs">
          <Search
            className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground"
            aria-hidden
          />
          <Input
            aria-label="Search documents"
            placeholder="Search documents…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="pl-9"
          />
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs tabular-nums text-muted-foreground">
            {visible.length} {visible.length === 1 ? "source" : "sources"}
          </span>
          <label className="sr-only" htmlFor="document-status-filter">
            Filter documents by status
          </label>
          <select
            id="document-status-filter"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            className="h-10 rounded-md border bg-card px-3 text-sm"
          >
            <option value="all">All statuses</option>
            <option value="ready">Ready</option>
            <option value="processing">Processing</option>
            <option value="failed">Failed</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>
      </div>
      {documents.loading && !documents.data ? (
        <div
          role="status"
          aria-label="Loading documents"
          className="space-y-3 rounded-xl border p-4"
        >
          {[0, 1, 2].map((n) => (
            <Skeleton key={n} className="h-14 w-full" />
          ))}
          <span className="sr-only">Loading documents…</span>
        </div>
      ) : !visible.length ? (
        <div className="flex min-h-56 flex-col items-center justify-center rounded-xl border border-dashed px-6 py-10 text-center">
          <Library className="mb-4 size-6 text-muted-foreground" aria-hidden />
          <h2 className="text-sm font-medium">
            {documents.data?.length
              ? "No matching documents"
              : "Your library starts here"}
          </h2>
          <p className="mt-2 max-w-sm text-sm text-muted-foreground">
            {documents.data?.length
              ? "Try a different search or status filter."
              : "Upload a PDF to ask questions, follow citations and return to the original pages."}
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card/30">
          <Table className="table-fixed">
            <TableHeader>
              <TableRow>
                <TableHead className="w-[56%] sm:w-auto">Document</TableHead>
                <TableHead className="w-28 sm:w-40">Status</TableHead>
                <TableHead className="hidden w-20 md:table-cell">
                  Pages
                </TableHead>
                <TableHead className="hidden w-24 lg:table-cell">
                  Chunks
                </TableHead>
                <TableHead className="w-12">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visible.map((doc) => {
                const latest = (jobs.data ?? [])
                  .filter((job) => job.document_id === doc.id)
                  .sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
                return (
                  <TableRow key={doc.id}>
                    <TableCell className="align-top">
                      <Link
                        href={`/documents/${doc.id}`}
                        className="flex min-w-0 items-start gap-3 rounded-sm font-medium hover:underline"
                      >
                        <FileText
                          className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                          aria-hidden
                        />
                        <span className="min-w-0 break-words text-sm">
                          {doc.filename}
                        </span>
                      </Link>
                      <p className="mt-1 pl-7 text-xs text-muted-foreground">
                        {processingSummary(doc.page_metadata)}
                      </p>
                      <p className="mt-1 pl-7 text-xs text-muted-foreground md:hidden">
                        {doc.pages} {doc.pages === 1 ? "page" : "pages"}
                      </p>
                    </TableCell>
                    <TableCell className="align-top">
                      <DocumentStatus status={doc.status} />
                      {latest && ["queued", "running"].includes(doc.status) && (
                        <div className="mt-2 max-w-32">
                          <Progress
                            value={boundedProgress(latest.progress)}
                            aria-label={`Processing ${doc.filename}`}
                          />
                          <span className="mt-1 block text-xs tabular-nums text-muted-foreground">
                            {boundedProgress(latest.progress)}%
                          </span>
                        </div>
                      )}
                      {doc.status === "failed" && (
                        <Link
                          href="/jobs"
                          className="mt-2 block text-xs underline underline-offset-4"
                        >
                          Review activity
                        </Link>
                      )}
                    </TableCell>
                    <TableCell className="hidden align-top tabular-nums text-muted-foreground md:table-cell">
                      {doc.pages}
                    </TableCell>
                    <TableCell className="hidden align-top tabular-nums text-muted-foreground lg:table-cell">
                      {doc.chunks}
                    </TableCell>
                    <TableCell className="align-top">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-8"
                            aria-label={`Actions for ${doc.filename}`}
                          >
                            <MoreHorizontal />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem asChild>
                            <Link href={`/documents/${doc.id}`}>
                              <ExternalLink className="mr-2 size-4" />
                              Open document
                            </Link>
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            onSelect={() => setPendingDelete(doc)}
                            className="text-destructive focus:text-destructive"
                            aria-label={`Delete ${doc.filename}`}
                          >
                            <Trash2 className="mr-2 size-4" />
                            Delete document
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
      <AlertDialog
        open={!!pendingDelete}
        onOpenChange={(open) => {
          if (!open && !deleting) setPendingDelete(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete document?</AlertDialogTitle>
            <AlertDialogDescription>
              Delete “{pendingDelete?.filename}” and its search index? Its PDF
              and source passages will no longer be available to your workspace.
              This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <ErrorNotice error={actionError} />
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>
              Keep document
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={(event) => {
                event.preventDefault();
                void remove();
              }}
              disabled={deleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleting ? "Deleting…" : "Delete document"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
