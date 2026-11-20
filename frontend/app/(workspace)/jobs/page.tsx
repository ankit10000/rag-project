"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  RefreshCw,
  X,
  RotateCcw,
  Activity,
  ArrowUpRight,
  Search,
  LoaderCircle,
} from "lucide-react";
import { api } from "@/lib/api";
import type { Job } from "@/lib/api-types";
import { boundedProgress } from "@/lib/document-ui";
import { useResource, ErrorNotice } from "@/components/workspace";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DocumentStatus } from "@/components/document-status";
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
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
export default function Jobs() {
  const { data, error, loading, refresh } = useResource(api.jobs);
  const documents = useResource(api.documents);
  const [actionError, setActionError] = useState<Error | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [pendingCancel, setPendingCancel] = useState<Job | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    const timer = setInterval(() => {
      if (!document.hidden) void refresh();
    }, 5000);
    return () => clearInterval(timer);
  }, [refresh]);
  async function action(job: Job, retry: boolean) {
    if (busy) return;
    setBusy(job.id);
    setActionError(null);
    setNotice("");
    try {
      await (retry ? api.retryJob(job.id) : api.cancelJob(job.id));
      setPendingCancel(null);
      setNotice(
        retry
          ? "A new processing attempt has been queued."
          : "Processing cancellation requested.",
      );
      await refresh();
    } catch (error) {
      setActionError(error as Error);
    } finally {
      setBusy(null);
    }
  }
  const nameFor = (id: string) =>
    documents.data?.find((doc) => doc.id === id)?.filename ?? "Document";
  const visible = (data ?? []).filter(
    (job) =>
      (filter === "all" ||
        (filter === "processing"
          ? ["queued", "running"].includes(job.status)
          : job.status === filter)) &&
      nameFor(job.document_id)
        .toLocaleLowerCase()
        .includes(search.toLocaleLowerCase()),
  );
  const active = (data ?? []).filter((job) =>
    ["queued", "running"].includes(job.status),
  ).length;
  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
            Behind your answers
          </p>
          <h1>Processing activity</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            PDF extraction, local OCR and indexing. Updates every five seconds.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => void refresh()}
          disabled={loading}
        >
          <RefreshCw
            className={loading ? "animate-spin motion-reduce:animate-none" : ""}
          />
          Refresh
        </Button>
      </div>
      <ErrorNotice error={error || actionError} />
      {notice && (
        <p
          role="status"
          className="rounded-lg border bg-secondary/50 px-4 py-3 text-sm"
        >
          {notice}
        </p>
      )}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full sm:max-w-xs">
          <Search
            className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground"
            aria-hidden
          />
          <Input
            aria-label="Search processing activity"
            placeholder="Search documents…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="pl-9"
          />
        </div>
        <div className="flex items-center gap-3">
          <p className="text-xs tabular-nums text-muted-foreground">
            {active} in progress
          </p>
          <label className="sr-only" htmlFor="job-status-filter">
            Filter activity by status
          </label>
          <select
            id="job-status-filter"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            className="h-10 rounded-md border bg-card px-3 text-sm"
          >
            <option value="all">All activity</option>
            <option value="processing">In progress</option>
            <option value="succeeded">Complete</option>
            <option value="failed">Failed</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>
      </div>
      {loading && !data ? (
        <div
          role="status"
          aria-label="Loading activity"
          className="space-y-3 rounded-xl border p-4"
        >
          {[0, 1, 2].map((n) => (
            <Skeleton key={n} className="h-16 w-full" />
          ))}
          <span className="sr-only">Loading activity…</span>
        </div>
      ) : !visible.length ? (
        <div className="flex min-h-56 flex-col items-center justify-center rounded-xl border border-dashed p-8 text-center">
          <Activity className="mb-4 size-6 text-muted-foreground" aria-hidden />
          <h2 className="text-sm font-medium">
            {data?.length ? "No matching activity" : "Nothing processing yet"}
          </h2>
          <p className="mt-2 max-w-sm text-sm text-muted-foreground">
            {data?.length
              ? "Try another search or status filter."
              : "Upload a PDF and follow its path from source pages to searchable evidence here."}
          </p>
          {!data?.length && (
            <Button variant="outline" asChild className="mt-5">
              <Link href="/documents">
                Open document library
                <ArrowUpRight />
              </Link>
            </Button>
          )}
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card/30">
          <Table className="table-fixed">
            <TableHeader>
              <TableRow>
                <TableHead>Document</TableHead>
                <TableHead className="w-28 sm:w-32">Status</TableHead>
                <TableHead className="hidden w-36 sm:table-cell">
                  Progress
                </TableHead>
                <TableHead className="hidden w-20 lg:table-cell">
                  Attempts
                </TableHead>
                <TableHead className="w-20 sm:w-28">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visible.map((job) => (
                <TableRow key={job.id}>
                  <TableCell className="min-w-0 align-top">
                    <Link
                      href={`/documents/${job.document_id}`}
                      className="break-words text-sm font-medium hover:underline"
                    >
                      {nameFor(job.document_id)}
                    </Link>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {new Date(job.created_at).toLocaleString(undefined, {
                        dateStyle: "medium",
                        timeStyle: "short",
                      })}
                    </p>
                    {job.error_code && (
                      <p className="mt-2 text-xs text-destructive">
                        Processing failed. Retry this job or replace the PDF.
                      </p>
                    )}
                    <div className="mt-2 max-w-36 sm:hidden">
                      <Progress
                        value={boundedProgress(job.progress)}
                        aria-label={`Processing progress for ${nameFor(job.document_id)}`}
                      />
                      <span className="mt-1 block text-xs tabular-nums text-muted-foreground">
                        {boundedProgress(job.progress)}%
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="align-top">
                    <DocumentStatus status={job.status} />
                  </TableCell>
                  <TableCell className="hidden align-top sm:table-cell">
                    <Progress
                      value={boundedProgress(job.progress)}
                      aria-label={`Processing progress for ${nameFor(job.document_id)}`}
                    />
                    <span className="mt-1 block text-xs tabular-nums text-muted-foreground">
                      {boundedProgress(job.progress)}%
                    </span>
                  </TableCell>
                  <TableCell className="hidden align-top tabular-nums text-muted-foreground lg:table-cell">
                    {job.attempts}
                  </TableCell>
                  <TableCell className="align-top">
                    {["queued", "running"].includes(job.status) ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={!!busy}
                        onClick={() => setPendingCancel(job)}
                        aria-label={`Cancel processing ${nameFor(job.document_id)}`}
                      >
                        <X />
                        <span className="hidden sm:inline">Cancel</span>
                      </Button>
                    ) : ["failed", "cancelled"].includes(job.status) ? (
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={!!busy}
                        onClick={() => void action(job, true)}
                        aria-label={`Retry processing ${nameFor(job.document_id)}`}
                      >
                        {busy === job.id ? (
                          <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                        ) : (
                          <RotateCcw />
                        )}
                        <span className="hidden sm:inline">Retry</span>
                      </Button>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <AlertDialog
        open={!!pendingCancel}
        onOpenChange={(open) => {
          if (!open && !busy) setPendingCancel(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Cancel processing?</AlertDialogTitle>
            <AlertDialogDescription>
              Stop processing “
              {pendingCancel ? nameFor(pendingCancel.document_id) : ""}”? The
              original uploaded PDF stays in your library. You can retry a
              cancelled job from this screen.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <ErrorNotice error={actionError} />
          <AlertDialogFooter>
            <AlertDialogCancel disabled={!!busy}>
              Keep processing
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={!!busy}
              onClick={(event) => {
                event.preventDefault();
                if (pendingCancel) void action(pendingCancel, false);
              }}
            >
              Cancel processing
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
