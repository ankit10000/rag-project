"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileText,
  MoreHorizontal,
  Replace,
  Trash2,
  LoaderCircle,
} from "lucide-react";
import { api, fileUrl } from "@/lib/api";
import { PdfPreview } from "@/components/pdf-preview";
import {
  pdfValidationError,
  processingSummary,
  boundedProgress,
} from "@/lib/document-ui";
import { useResource, ErrorNotice } from "@/components/workspace";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DocumentStatus } from "@/components/document-status";
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
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
export function DocumentDetail({
  id,
  initialPage = 1,
}: {
  id: string;
  initialPage?: number;
}) {
  const router = useRouter();
  const loader = useCallback(() => api.document(id), [id]);
  const { data, error, loading, refresh } = useResource(loader);
  const jobs = useResource(api.jobs);
  const [page, setPage] = useState(initialPage);
  const [busy, setBusy] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [actionError, setActionError] = useState<Error | null>(null);
  const [notice, setNotice] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const { refresh: refreshJobs } = jobs;
  useEffect(() => {
    if (!data || !["queued", "running"].includes(data.status)) return;
    const timer = setInterval(() => {
      if (!document.hidden) {
        void refresh();
        void refreshJobs();
      }
    }, 5000);
    return () => clearInterval(timer);
  }, [data, refresh, refreshJobs]);
  function chooseReplacement(file: File | undefined) {
    if (!file) return;
    setActionError(null);
    const invalid = pdfValidationError(file);
    if (invalid) {
      setActionError(new Error(invalid));
      return;
    }
    setPendingFile(file);
  }
  async function replace() {
    if (!pendingFile || busy) return;
    setBusy(true);
    setActionError(null);
    setNotice("");
    try {
      await api.replaceDocument(id, pendingFile);
      setPendingFile(null);
      setPage(1);
      setNotice(
        "Replacement received. OCR and indexing will continue in Activity.",
      );
      await Promise.all([refresh(), refreshJobs()]);
    } catch (error) {
      setActionError(error as Error);
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (busy) return;
    setBusy(true);
    setActionError(null);
    try {
      await api.deleteDocument(id);
      router.push("/documents");
      router.refresh();
    } catch (error) {
      setActionError(error as Error);
      setBusy(false);
    }
  }
  const totalPages = Math.max(data?.pages || 1, 1);
  const currentPage = Math.min(totalPages, Math.max(1, Math.floor(page) || 1));
  const latest = (jobs.data ?? [])
    .filter((job) => job.document_id === id)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  return (
    <>
      <Link
        href="/documents"
        className="inline-flex w-fit items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden />
        Documents
      </Link>
      <ErrorNotice error={error || actionError} />
      {notice && (
        <p
          role="status"
          className="rounded-lg border bg-secondary/50 px-4 py-3 text-sm"
        >
          {notice}{" "}
          <Link href="/jobs" className="underline underline-offset-4">
            View activity
          </Link>
        </p>
      )}
      {loading && !data ? (
        <div role="status" aria-label="Loading source" className="space-y-5">
          <Skeleton className="h-10 w-2/3" />
          <Skeleton className="h-96 w-full" />
          <span className="sr-only">Loading source…</span>
        </div>
      ) : (
        data && (
          <>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="mb-3 flex items-center gap-2">
                  <FileText
                    className="size-4 text-muted-foreground"
                    aria-hidden
                  />
                  <DocumentStatus status={data.status} />
                </div>
                <h1 className="break-words text-2xl sm:text-3xl">
                  {data.filename}
                </h1>
                <p className="mt-2 text-sm text-muted-foreground">
                  {data.pages} {data.pages === 1 ? "page" : "pages"} ·{" "}
                  {data.chunks} searchable chunks ·{" "}
                  {processingSummary(data.page_metadata)}
                </p>
              </div>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="Source actions"
                    disabled={busy}
                  >
                    <MoreHorizontal />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onSelect={() => input.current?.click()}>
                    <Replace className="mr-2 size-4" />
                    Replace PDF
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onSelect={() => setDeleteOpen(true)}
                    className="text-destructive focus:text-destructive"
                  >
                    <Trash2 className="mr-2 size-4" />
                    Delete document
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
            <label className="sr-only" htmlFor="replacement-pdf">
              Replace PDF
            </label>
            <input
              ref={input}
              id="replacement-pdf"
              type="file"
              accept="application/pdf,.pdf"
              disabled={busy}
              className="sr-only"
              onChange={(event) => {
                chooseReplacement(event.target.files?.[0]);
                event.target.value = "";
              }}
            />
            {latest && ["queued", "running"].includes(data.status) && (
              <div role="status" className="rounded-xl border bg-card p-4">
                <div className="mb-3 flex items-center justify-between gap-3 text-sm">
                  <span className="flex items-center gap-2">
                    <LoaderCircle
                      className="size-4 animate-spin motion-reduce:animate-none"
                      aria-hidden
                    />
                    {data.status === "queued"
                      ? "Waiting for a processing worker"
                      : "Processing source pages and search index"}
                  </span>
                  <span className="tabular-nums text-muted-foreground">
                    {boundedProgress(latest.progress)}%
                  </span>
                </div>
                <Progress
                  value={boundedProgress(latest.progress)}
                  aria-label="Document processing progress"
                />
                <Link
                  href="/jobs"
                  className="mt-3 inline-block text-xs underline underline-offset-4"
                >
                  View processing activity
                </Link>
              </div>
            )}
            {data.status === "failed" && (
              <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm">
                <p>
                  Document processing failed. Open activity to retry the job or
                  replace the PDF.
                </p>
                <Link
                  href="/jobs"
                  className="mt-2 inline-block underline underline-offset-4"
                >
                  Review activity
                </Link>
              </div>
            )}
            <Tabs defaultValue="preview" className="min-w-0">
              <TabsList>
                <TabsTrigger value="preview">PDF preview</TabsTrigger>
                <TabsTrigger value="processing">Page details</TabsTrigger>
              </TabsList>
              <TabsContent value="preview" className="mt-5 space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <Button
                      size="icon"
                      variant="outline"
                      aria-label="Previous page"
                      onClick={() => setPage(currentPage - 1)}
                      disabled={currentPage <= 1}
                    >
                      <ChevronLeft />
                    </Button>
                    <label htmlFor="page" className="sr-only">
                      Original page
                    </label>
                    <Input
                      id="page"
                      type="number"
                      min={1}
                      max={totalPages}
                      value={currentPage}
                      className="w-16 text-center tabular-nums"
                      onChange={(event) =>
                        setPage(
                          Math.min(
                            totalPages,
                            Math.max(
                              1,
                              Math.floor(Number(event.target.value)) || 1,
                            ),
                          ),
                        )
                      }
                    />
                    <span className="text-sm text-muted-foreground">
                      of {data.pages || "—"}
                    </span>
                    <Button
                      size="icon"
                      variant="outline"
                      aria-label="Next page"
                      onClick={() => setPage(currentPage + 1)}
                      disabled={currentPage >= totalPages}
                    >
                      <ChevronRight />
                    </Button>
                  </div>
                  <Button variant="outline" asChild>
                    <a
                      href={fileUrl(id, currentPage)}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <ExternalLink />
                      Open PDF
                    </a>
                  </Button>
                </div>
                <PdfPreview
                  id={id}
                  page={currentPage}
                  filename={data.filename}
                />
                <p className="text-xs text-muted-foreground">
                  Page numbers refer to the original PDF. Source access follows
                  your account permissions.
                </p>
              </TabsContent>
              <TabsContent value="processing" className="mt-5">
                <section
                  className="overflow-hidden rounded-xl border bg-card/30"
                  aria-label="Original page processing details"
                >
                  <div className="border-b p-5">
                    <h2 className="text-sm font-medium">
                      How this source was processed
                    </h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {processingSummary(data.page_metadata)}
                    </p>
                  </div>
                  {data.page_metadata?.length ? (
                    <ul className="divide-y divide-border/60">
                      {data.page_metadata.map((metadata, index) => {
                        const number =
                          typeof metadata.page_number === "number"
                            ? metadata.page_number
                            : null;
                        const method =
                          metadata.method === "native"
                            ? "Native text"
                            : typeof metadata.method === "string" &&
                                metadata.method.startsWith("pymupdf-tesseract")
                              ? "Local OCR"
                              : "Not reported";
                        return (
                          <li
                            key={index}
                            className="flex items-center justify-between gap-3 px-5 py-3 text-sm"
                          >
                            <span>
                              {number ? `Page ${number}` : "Page not reported"}
                            </span>
                            <span className="text-muted-foreground">
                              {method}
                            </span>
                          </li>
                        );
                      })}
                    </ul>
                  ) : (
                    <p className="p-5 text-sm text-muted-foreground">
                      Page details will appear after processing.
                    </p>
                  )}
                </section>
              </TabsContent>
            </Tabs>
          </>
        )
      )}
      <AlertDialog
        open={!!pendingFile}
        onOpenChange={(open) => {
          if (!open && !busy) setPendingFile(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Replace document?</AlertDialogTitle>
            <AlertDialogDescription>
              Replace “{data?.filename}” with “{pendingFile?.name}”? The current
              search index will be replaced, and existing processing for this
              source will be cancelled. The replacement must finish indexing
              before it is ready for answers.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <ErrorNotice error={actionError} />
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>
              Keep current PDF
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={busy}
              onClick={(event) => {
                event.preventDefault();
                void replace();
              }}
            >
              {busy ? "Uploading replacement…" : "Replace PDF"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <AlertDialog
        open={deleteOpen}
        onOpenChange={(open) => {
          if (!open && !busy) setDeleteOpen(false);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete document?</AlertDialogTitle>
            <AlertDialogDescription>
              Delete “{data?.filename}” and its search index? The source PDF and
              its passages will no longer be available. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <ErrorNotice error={actionError} />
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Keep document</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={busy}
              onClick={(event) => {
                event.preventDefault();
                void remove();
              }}
            >
              {busy ? "Deleting…" : "Delete document"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
