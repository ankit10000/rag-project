"use client";

import { useEffect, useRef, useState } from "react";
import type {
  PDFDocumentLoadingTask,
  PDFPageProxy,
  PDFWorker,
  RenderTask,
} from "pdfjs-dist/types/src/display/api";
import { ExternalLink, LoaderCircle, FileWarning } from "lucide-react";
import { fileUrl } from "@/lib/api";
import { Button } from "@/components/ui/button";

const MAX_PDF_BYTES = 25 * 1024 * 1024;
const MAX_CANVAS_PIXELS = 6_000_000;

type PreviewState = {
  key: string;
  status: "loading" | "ready" | "error";
};

/** Canvas-only PDF rendering: no PDF scripting, forms or HTML annotations. */
export function PdfPreview({
  id,
  page,
  filename,
}: {
  id: string;
  page: number;
  filename: string;
}) {
  const container = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [state, setState] = useState<PreviewState | null>(null);
  const originalPage = Math.max(1, Math.floor(page) || 1);
  const key = `${id}:${originalPage}`;
  const status = state?.key === key ? state.status : "loading";

  useEffect(() => {
    const element = container.current;
    const target = canvas.current;
    if (!element || !target) return;

    let disposed = false;
    let worker: Worker | null = null;
    let pdfWorker: PDFWorker | null = null;
    let loadingTask: PDFDocumentLoadingTask | null = null;
    let pageProxy: PDFPageProxy | null = null;
    let renderTask: RenderTask | null = null;
    let renderChain: Promise<void> = Promise.resolve();
    let revision = 0;
    let frame = 0;
    let lastWidth = 0;
    let pdfjs: typeof import("pdfjs-dist") | null = null;
    const controller = new AbortController();

    function fail(error: unknown) {
      if (
        disposed ||
        (error instanceof Error &&
          ["AbortError", "RenderingCancelledException"].includes(error.name))
      )
        return;
      // Never surface PDF/parser/private HTTP error text in the interface.
      setState({ key, status: "error" });
    }

    function scheduleRender() {
      if (disposed || !pageProxy || !pdfjs) return;
      const width = Math.floor(element!.getBoundingClientRect().width);
      if (width <= 0 || width === lastWidth) return;
      lastWidth = width;
      const ticket = ++revision;
      renderTask?.cancel();
      const sourcePage = pageProxy;
      const library = pdfjs;
      renderChain = renderChain
        .catch(() => {})
        .then(async () => {
          if (disposed || ticket !== revision) return;
          setState({ key, status: "loading" });
          const base = sourcePage.getViewport({ scale: 1 });
          if (
            !Number.isFinite(base.width) ||
            !Number.isFinite(base.height) ||
            base.width <= 0 ||
            base.height <= 0
          )
            throw new Error("Invalid page size");
          // Fit original aspect ratio; avoid unbounded bitmaps from unusual PDFs.
          const scale = Math.min(
            Math.max(width - 24, 1) / base.width,
            1200 / base.width,
            2400 / base.height,
          );
          const viewport = sourcePage.getViewport({ scale });
          const ratio = Math.min(
            window.devicePixelRatio || 1,
            2,
            Math.sqrt(MAX_CANVAS_PIXELS / (viewport.width * viewport.height)),
          );
          target!.width = Math.max(1, Math.floor(viewport.width * ratio));
          target!.height = Math.max(1, Math.floor(viewport.height * ratio));
          target!.style.width = `${viewport.width}px`;
          target!.style.height = `${viewport.height}px`;
          const task = sourcePage.render({
            canvas: target!,
            viewport,
            transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
            annotationMode: library.AnnotationMode.DISABLE,
            background: "rgb(255,255,255)",
          });
          renderTask = task;
          await task.promise;
          if (!disposed && ticket === revision)
            setState({ key, status: "ready" });
        })
        .catch(fail);
    }

    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(scheduleRender);
    });
    observer.observe(element);

    async function load() {
      // Import only in the browser: PDF.js accesses browser graphics globals.
      pdfjs = await import("pdfjs-dist");
      if (disposed) return;
      worker = new Worker(
        new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url),
        { type: "module" },
      );
      pdfjs.GlobalWorkerOptions.workerPort = worker;
      pdfWorker = pdfjs.PDFWorker.create({ port: worker });
      const response = await fetch(fileUrl(id, 1).split("#")[0], {
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("Source unavailable");
      const length = Number(response.headers.get("Content-Length"));
      if (Number.isFinite(length) && length > MAX_PDF_BYTES)
        throw new Error("PDF too large");
      const bytes = new Uint8Array(await response.arrayBuffer());
      if (disposed) return;
      if (!bytes.length || bytes.length > MAX_PDF_BYTES)
        throw new Error("Invalid PDF size");
      const options = {
        data: bytes,
        worker: pdfWorker,
        withCredentials: true,
        enableXfa: false,
        isEvalSupported: false,
        useWorkerFetch: false,
        useWasm: false,
        isOffscreenCanvasSupported: false,
        maxImageSize: 16_000_000,
        canvasMaxAreaInBytes: 32 * 1024 * 1024,
        verbosity: pdfjs.VerbosityLevel.ERRORS,
      };
      loadingTask = pdfjs.getDocument(options);
      const document = await loadingTask.promise;
      if (disposed) return;
      if (originalPage > document.numPages) throw new Error("Page unavailable");
      pageProxy = await document.getPage(originalPage);
      if (!disposed) scheduleRender();
    }
    void load().catch(fail);

    return () => {
      disposed = true;
      revision++;
      controller.abort();
      observer.disconnect();
      cancelAnimationFrame(frame);
      renderTask?.cancel();
      const ownedWorker = worker;
      const ownedPDFWorker = pdfWorker;
      // Destroy pending document/render work before terminating its local worker.
      void Promise.resolve(loadingTask?.destroy())
        .catch(() => {})
        .finally(() => {
          if (pdfjs?.GlobalWorkerOptions.workerPort === ownedWorker)
            pdfjs.GlobalWorkerOptions.workerPort = null;
          ownedPDFWorker?.destroy();
          ownedWorker?.terminate();
        });
    };
  }, [id, originalPage, key]);

  return (
    <figure
      className="min-w-0 overflow-hidden rounded-xl border bg-card/40"
      aria-label={`PDF source: ${filename}, page ${originalPage}`}
    >
      <div
        ref={container}
        className="relative flex min-h-80 w-full justify-center overflow-hidden px-3 py-4"
        aria-busy={status === "loading"}
      >
        <canvas
          ref={canvas}
          role="img"
          aria-label={`Original PDF page ${originalPage}`}
          data-pdf-page={originalPage}
          data-render-state={status}
          data-rendered-page={status === "ready" ? originalPage : undefined}
          data-render-complete={status === "ready" ? "true" : "false"}
          className={`max-w-full self-start bg-white shadow-sm ${status === "ready" ? "" : "invisible"}`}
        />
        {status === "loading" && (
          <div
            role="status"
            className="absolute inset-0 flex items-center justify-center gap-2 p-6 text-sm text-muted-foreground"
          >
            <LoaderCircle
              className="size-4 animate-spin motion-reduce:animate-none"
              aria-hidden
            />
            Loading original page {originalPage}…
          </div>
        )}
        {status === "error" && (
          <div
            role="alert"
            className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center"
          >
            <FileWarning className="size-6 text-muted-foreground" aria-hidden />
            <p className="text-sm">This page could not be previewed.</p>
            <p className="max-w-sm text-xs text-muted-foreground">
              Open the original PDF to view it, or return to the library to
              check source availability.
            </p>
            <Button variant="outline" asChild>
              <a
                href={fileUrl(id, originalPage)}
                target="_blank"
                rel="noopener noreferrer"
              >
                <ExternalLink />
                Open the original PDF
              </a>
            </Button>
          </div>
        )}
      </div>
      <figcaption className="border-t px-4 py-3 text-xs text-muted-foreground">
        Original page {originalPage} · {filename}
      </figcaption>
    </figure>
  );
}
