/** Client presentation only. The backend remains authoritative for PDF validation. */
export const MAX_PDF_BYTES = 25 * 1024 * 1024;
export function pdfValidationError(file: {
  name: string;
  size: number;
  type: string;
}): string | null {
  if (
    !file.name.toLowerCase().endsWith(".pdf") ||
    (file.type && file.type !== "application/pdf")
  )
    return "Choose a PDF file (.pdf).";
  if (file.size === 0) return "This PDF is empty. Choose a file with content.";
  if (file.size > MAX_PDF_BYTES) return "Choose a PDF of 25 MB or less.";
  return null;
}
export function processingSummary(
  metadata: { [key: string]: unknown }[] = [],
): string {
  const native = metadata.filter((page) => page.method === "native").length;
  const ocr = metadata.filter(
    (page) =>
      typeof page.method === "string" &&
      page.method.startsWith("pymupdf-tesseract"),
  ).length;
  if (native && ocr)
    return `${native} native · ${ocr} OCR ${ocr === 1 ? "page" : "pages"}`;
  if (ocr) return `${ocr} OCR ${ocr === 1 ? "page" : "pages"}`;
  if (native) return `${native} native ${native === 1 ? "page" : "pages"}`;
  return "Page processing details pending";
}
export function boundedProgress(value: number): number {
  return Number.isFinite(value) ? Math.min(100, Math.max(0, value)) : 0;
}
