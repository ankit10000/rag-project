import test from "node:test";
import assert from "node:assert/strict";
import {
  MAX_PDF_BYTES,
  pdfValidationError,
  processingSummary,
  boundedProgress,
} from "../lib/document-ui.ts";
test("PDF upload accepts the exact25MB boundary and refuses empty, oversize or wrong type", () => {
  assert.equal(
    pdfValidationError({
      name: "Source.PDF",
      type: "application/pdf",
      size: MAX_PDF_BYTES,
    }),
    null,
  );
  assert.match(
    pdfValidationError({
      name: "Source.pdf",
      type: "application/pdf",
      size: MAX_PDF_BYTES + 1,
    }),
    /25 MB/,
  );
  assert.match(
    pdfValidationError({
      name: "Source.pdf",
      type: "application/pdf",
      size: 0,
    }),
    /empty/,
  );
  assert.match(
    pdfValidationError({ name: "Source.txt", type: "text/plain", size: 12 }),
    /PDF/,
  );
  assert.match(
    pdfValidationError({ name: "Source.pdf", type: "text/html", size: 12 }),
    /PDF/,
  );
  assert.equal(
    pdfValidationError({ name: "Source.pdf", type: "", size: 12 }),
    null,
  );
});
test("processing labels reflect reported native/OCR evidence, never infer OCR from readiness", () => {
  assert.equal(processingSummary(), "Page processing details pending");
  assert.equal(
    processingSummary([
      { method: "native" },
      { method: "pymupdf-tesseract-fast-4.1.0" },
    ]),
    "1 native · 1 OCR page",
  );
  assert.equal(
    processingSummary([{ method: "native" }, { method: "native" }]),
    "2 native pages",
  );
  assert.equal(
    processingSummary([{ method: "unknown" }]),
    "Page processing details pending",
  );
});
test("progress remains within the real reported percentage bounds", () => {
  assert.equal(boundedProgress(37), 37);
  assert.equal(boundedProgress(1000), 100);
  assert.equal(boundedProgress(-5), 0);
  assert.equal(boundedProgress(NaN), 0);
});
