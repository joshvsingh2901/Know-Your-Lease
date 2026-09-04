"use client";

import { useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";

import { getDocumentPdfUrl } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";
import {
  clearCitationHighlight,
  highlightCitationSnippet,
} from "@/lib/pdf-text-highlight";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

interface PdfViewerClientProps {
  documentId: string;
  pageNumber: number;
  highlightText: string | null;
  onPageChange: (pageNumber: number) => void;
}

export function PdfViewerClient({
  documentId,
  pageNumber,
  highlightText,
  onPageChange,
}: PdfViewerClientProps) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const pageRef = useRef<HTMLDivElement>(null);
  const [numPages, setNumPages] = useState(0);
  const [pageWidth, setPageWidth] = useState(0);
  const [loadError, setLoadError] = useState(false);
  const [renderedTextPage, setRenderedTextPage] = useState<number | null>(null);
  const [fileSource, setFileSource] = useState<
    { documentId: string; url: string; httpHeaders?: Record<string, string> } | null
  >(null);
  const currentPage = numPages ? Math.min(Math.max(pageNumber, 1), numPages) : pageNumber;
  // Stale while a new token/documentId is resolving: rendered as "not ready yet"
  // instead of clearing state synchronously inside the effect below.
  const readyFileSource = fileSource?.documentId === documentId ? fileSource : null;

  useEffect(() => {
    let isCurrent = true;
    void getAccessToken().then((token) => {
      if (!isCurrent) return;
      setFileSource({
        documentId,
        url: getDocumentPdfUrl(documentId),
        ...(token ? { httpHeaders: { Authorization: `Bearer ${token}` } } : {}),
      });
    });
    return () => {
      isCurrent = false;
    };
  }, [documentId]);

  useEffect(() => {
    const element = viewportRef.current;
    if (!element) return;

    const resizeObserver = new ResizeObserver(([entry]) => {
      setPageWidth(Math.max(240, Math.floor(entry.contentRect.width - 32)));
    });
    resizeObserver.observe(element);
    return () => resizeObserver.disconnect();
  }, []);

  useEffect(() => {
    const pageElement = pageRef.current;
    if (!pageElement || renderedTextPage !== currentPage) return;
    if (!highlightText) {
      clearCitationHighlight(pageElement);
      return;
    }
    highlightCitationSnippet(pageElement, highlightText);
  }, [currentPage, highlightText, renderedTextPage]);

  function handleLoadSuccess({ numPages: loadedPages }: { numPages: number }) {
    setNumPages(loadedPages);
    onPageChange(Math.min(Math.max(pageNumber, 1), loadedPages));
    setLoadError(false);
  }

  return (
    <section className="overflow-hidden rounded-2xl border border-[var(--line)] bg-white shadow-[0_18px_60px_rgba(19,43,58,0.08)]">
      <div className="flex items-center justify-between gap-4 border-b border-[var(--line)] px-5 py-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--accent)]">
            Original lease
          </p>
          <h2 className="mt-1 font-serif text-xl text-[var(--navy)]">Source document</h2>
        </div>
        <span className="rounded-full border border-[var(--line)] bg-[var(--paper)] px-3 py-1 font-mono text-xs text-[var(--muted)]">
          {numPages ? `Page ${currentPage} / ${numPages}` : "Loading"}
        </span>
      </div>

      <div ref={viewportRef} className="min-h-[32.5rem] bg-[#e7e6e1] p-4 sm:p-6">
        {loadError ? (
          <div className="grid min-h-[27.5rem] place-items-center rounded-xl border border-[#ebc4bf] bg-[var(--error-bg)] p-6 text-center text-sm leading-6 text-[var(--error)]">
            The lease PDF could not be displayed. You can still review its cited source excerpts.
          </div>
        ) : !readyFileSource ? (
          <div className="grid min-h-[27.5rem] place-items-center text-sm text-[var(--muted)]">
            Loading PDF…
          </div>
        ) : (
          <Document
            file={readyFileSource}
            loading={
              <div className="grid min-h-[27.5rem] place-items-center text-sm text-[var(--muted)]">
                Loading PDF…
              </div>
            }
            onLoadSuccess={handleLoadSuccess}
            onLoadError={() => setLoadError(true)}
            onSourceError={() => setLoadError(true)}
            error={
              <div className="grid min-h-[27.5rem] place-items-center rounded-xl border border-[#ebc4bf] bg-[var(--error-bg)] p-6 text-center text-sm leading-6 text-[var(--error)]">
                The lease PDF could not be displayed. You can still review its cited source excerpts.
              </div>
            }
          >
            <div className="flex justify-center">
              <div ref={pageRef}>
                <Page
                  key={`${documentId}-${currentPage}`}
                  pageNumber={currentPage}
                  width={pageWidth || undefined}
                  renderAnnotationLayer={false}
                  renderTextLayer
                  onRenderTextLayerSuccess={() => setRenderedTextPage(currentPage)}
                  onRenderTextLayerError={() => setRenderedTextPage(null)}
                  loading={<div className="min-h-[27.5rem]" />}
                />
              </div>
            </div>
          </Document>
        )}
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-[var(--line)] px-5 py-4">
        <button
          type="button"
          disabled={currentPage <= 1 || loadError}
          onClick={() => onPageChange(Math.max(1, currentPage - 1))}
          className="rounded-lg border border-[var(--line)] px-3 py-2 text-sm font-semibold text-[var(--navy)] hover:border-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-45"
        >
          Previous
        </button>
        <p className="text-center text-xs text-[var(--muted)]" aria-live="polite">
          {numPages ? `Viewing page ${currentPage} of ${numPages}` : "Preparing pages"}
        </p>
        <button
          type="button"
          disabled={!numPages || currentPage >= numPages || loadError}
          onClick={() => onPageChange(Math.min(numPages, currentPage + 1))}
          className="rounded-lg border border-[var(--line)] px-3 py-2 text-sm font-semibold text-[var(--navy)] hover:border-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-45"
        >
          Next
        </button>
      </div>
    </section>
  );
}
