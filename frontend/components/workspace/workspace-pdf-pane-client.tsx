"use client";

import {
  memo,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";

import { getDocumentPdfUrl } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";
import { clearCitationHighlight, highlightCitationSnippet } from "@/lib/pdf-text-highlight";

import {
  clampPdfPage,
  estimatePdfPageHeight,
  getAnchoredScrollTop,
  getCurrentPageFromViewport,
  getPassageScrollTop,
  getRenderedPageNumbers,
} from "./pdf-viewer-utils";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

const ACCENT = "var(--l-accent)";
const MIN_ZOOM = 80;
const MAX_ZOOM = 150;
const ZOOM_STEP = 10;
const PAGE_GAP = 18;

interface WorkspacePdfPaneClientProps {
  documentId: string;
  currentPage: number;
  onPageChange: (pageNumber: number) => void;
  onNumPagesChange: (numPages: number) => void;
  highlightText: string | null;
  highlightPageNumber: number | null;
  highlightQuestion: string | null;
  highlightRequestId: number;
  onClearHighlight: () => void;
  hidden?: boolean;
}

interface LoadedPdfPage {
  pageNumber: number;
  originalWidth: number;
  originalHeight: number;
}

interface ZoomAnchor {
  pageNumber: number;
  relativeOffset: number;
}

type HighlightStatus = "idle" | "locating" | "visible" | "not-found";

interface TextLayerRender {
  pageNumber: number | null;
  revision: number;
}

interface HighlightResult {
  requestId: number;
  status: HighlightStatus;
}

function getPageTopInViewport(viewport: HTMLElement, page: HTMLElement): number {
  return page.getBoundingClientRect().top - viewport.getBoundingClientRect().top + viewport.scrollTop;
}

export function WorkspacePdfPaneClient({
  documentId,
  currentPage,
  onPageChange,
  onNumPagesChange,
  highlightText,
  highlightPageNumber,
  highlightQuestion,
  highlightRequestId,
  onClearHighlight,
  hidden = false,
}: WorkspacePdfPaneClientProps) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const pageElementsRef = useRef(new Map<number, HTMLDivElement>());
  const scrollFrameRef = useRef<number | null>(null);
  const lastScrollReportedPageRef = useRef<number | null>(null);
  const zoomAnchorRef = useRef<ZoomAnchor | null>(null);
  const lastScrolledHighlightRef = useRef<string | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [containerWidth, setContainerWidth] = useState(0);
  const [zoom, setZoom] = useState(100);
  const [loadError, setLoadError] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [pageAspectRatios, setPageAspectRatios] = useState<Record<number, number>>({});
  const [highlightResult, setHighlightResult] = useState<HighlightResult>({
    requestId: 0,
    status: "idle",
  });
  const [textLayerRender, setTextLayerRender] = useState<TextLayerRender>({
    pageNumber: null,
    revision: 0,
  });
  const [fileSource, setFileSource] = useState<
    { documentId: string; reloadKey: number; url: string; httpHeaders?: Record<string, string> } | null
  >(null);

  const displayedPage = clampPdfPage(currentPage, numPages);
  const readyFileSource =
    fileSource?.documentId === documentId && fileSource.reloadKey === reloadKey ? fileSource : null;
  const pageWidth = containerWidth ? Math.round((containerWidth * zoom) / 100) : 0;
  const highlightStatus: HighlightStatus = !highlightText
    ? "idle"
    : highlightResult.requestId === highlightRequestId
      ? highlightResult.status
      : "locating";
  const renderedPages = useMemo(
    () => new Set(getRenderedPageNumbers(displayedPage, numPages, highlightPageNumber)),
    [displayedPage, highlightPageNumber, numPages],
  );

  useEffect(() => {
    let isCurrent = true;
    void getAccessToken().then((token) => {
      if (!isCurrent) return;
      setFileSource({
        documentId,
        reloadKey,
        url: getDocumentPdfUrl(documentId),
        ...(token ? { httpHeaders: { Authorization: `Bearer ${token}` } } : {}),
      });
    });
    return () => {
      isCurrent = false;
    };
  }, [documentId, reloadKey]);

  useEffect(() => {
    const element = viewportRef.current;
    if (!element) return;
    const resizeObserver = new ResizeObserver(([entry]) => {
      setContainerWidth(Math.max(240, Math.floor(entry.contentRect.width - 40)));
    });
    resizeObserver.observe(element);
    return () => resizeObserver.disconnect();
  }, []);

  const setPageElement = useCallback((pageNumber: number, element: HTMLDivElement | null) => {
    if (element) pageElementsRef.current.set(pageNumber, element);
    else pageElementsRef.current.delete(pageNumber);
  }, []);

  const reportCurrentPage = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport || numPages < 1) return;

    const viewportRect = viewport.getBoundingClientRect();
    const metrics = [...pageElementsRef.current.entries()].map(([pageNumber, element]) => {
      const rect = element.getBoundingClientRect();
      return { pageNumber, top: rect.top, bottom: rect.bottom };
    });
    const nextPage = getCurrentPageFromViewport(metrics, viewportRect.top, viewportRect.height);
    if (nextPage !== null && nextPage !== displayedPage) {
      lastScrollReportedPageRef.current = nextPage;
      onPageChange(nextPage);
    }
  }, [displayedPage, numPages, onPageChange]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;

    function onScroll() {
      if (scrollFrameRef.current !== null) cancelAnimationFrame(scrollFrameRef.current);
      scrollFrameRef.current = requestAnimationFrame(() => {
        scrollFrameRef.current = null;
        reportCurrentPage();
      });
    }

    viewport.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      viewport.removeEventListener("scroll", onScroll);
      if (scrollFrameRef.current !== null) cancelAnimationFrame(scrollFrameRef.current);
    };
  }, [reportCurrentPage]);

  useLayoutEffect(() => {
    if (hidden || numPages < 1) return;
    if (lastScrollReportedPageRef.current === displayedPage) {
      lastScrollReportedPageRef.current = null;
      return;
    }

    const viewport = viewportRef.current;
    const page = pageElementsRef.current.get(displayedPage);
    if (viewport && page) {
      viewport.scrollTo({ top: Math.max(0, getPageTopInViewport(viewport, page) - 12), behavior: "auto" });
    }
  }, [displayedPage, hidden, numPages]);

  useLayoutEffect(() => {
    const anchor = zoomAnchorRef.current;
    if (!anchor) return;

    const frame = requestAnimationFrame(() => {
      const viewport = viewportRef.current;
      const page = pageElementsRef.current.get(anchor.pageNumber);
      if (viewport && page) {
        viewport.scrollTop = getAnchoredScrollTop(
          getPageTopInViewport(viewport, page),
          page.offsetHeight,
          anchor.relativeOffset,
        );
      }
      zoomAnchorRef.current = null;
    });
    return () => cancelAnimationFrame(frame);
  }, [zoom]);

  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      for (const page of pageElementsRef.current.values()) clearCitationHighlight(page);
      if (!highlightText || highlightPageNumber === null || hidden) {
        lastScrolledHighlightRef.current = null;
        setHighlightResult({ requestId: highlightRequestId, status: "idle" });
        return;
      }

      const pageElement = pageElementsRef.current.get(highlightPageNumber);
      if (!pageElement) {
        setHighlightResult({ requestId: highlightRequestId, status: "locating" });
        return;
      }

      const textLayer = pageElement.querySelector(".react-pdf__Page__textContent");
      if (!textLayer || textLayerRender.pageNumber !== highlightPageNumber) {
        setHighlightResult({ requestId: highlightRequestId, status: "locating" });
        return;
      }

      if (!highlightCitationSnippet(pageElement, highlightText)) {
        setHighlightResult({ requestId: highlightRequestId, status: "not-found" });
        return;
      }

      setHighlightResult({ requestId: highlightRequestId, status: "visible" });
      const highlightKey = `${highlightRequestId}:${highlightPageNumber}:${highlightText}`;
      if (lastScrolledHighlightRef.current === highlightKey) return;
      lastScrolledHighlightRef.current = highlightKey;

      const viewport = viewportRef.current;
      const highlightedSpan = pageElement.querySelector<HTMLElement>(
        '[data-citation-highlight-overlay="true"], [data-citation-highlight="true"]',
      );
      if (!viewport || !highlightedSpan) return;
      const viewportRect = viewport.getBoundingClientRect();
      const passageRect = highlightedSpan.getBoundingClientRect();
      viewport.scrollTo({
        top: getPassageScrollTop(
          viewport.scrollTop,
          viewportRect.top,
          viewportRect.height,
          passageRect.top,
        ),
        behavior: "auto",
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [
    hidden,
    highlightPageNumber,
    highlightRequestId,
    highlightText,
    textLayerRender.pageNumber,
    textLayerRender.revision,
  ]);

  const handleTextLayerRendered = useCallback((pageNumber: number) => {
    setTextLayerRender((current) => ({
      pageNumber,
      revision: current.revision + 1,
    }));
  }, []);

  const handleTextLayerError = useCallback((pageNumber: number) => {
    setTextLayerRender((current) => ({
      pageNumber,
      revision: current.revision + 1,
    }));
    setHighlightResult({ requestId: highlightRequestId, status: "not-found" });
  }, [highlightRequestId]);

  function handleLoadSuccess({ numPages: loadedPages }: { numPages: number }) {
    setNumPages(loadedPages);
    onNumPagesChange(loadedPages);
    onPageChange(clampPdfPage(currentPage, loadedPages));
    setLoadError(false);
  }

  const handlePageLoad = useCallback((page: LoadedPdfPage) => {
    if (page.originalWidth <= 0 || page.originalHeight <= 0) return;
    const nextRatio = page.originalHeight / page.originalWidth;
    setPageAspectRatios((current) =>
      Math.abs((current[page.pageNumber] ?? 0) - nextRatio) < 0.001
        ? current
        : { ...current, [page.pageNumber]: nextRatio },
    );
  }, []);

  function requestPage(pageNumber: number) {
    onPageChange(clampPdfPage(pageNumber, numPages));
  }

  function changeZoom(delta: number) {
    const viewport = viewportRef.current;
    const page = pageElementsRef.current.get(displayedPage);
    if (viewport && page && page.offsetHeight > 0) {
      const pageTop = getPageTopInViewport(viewport, page);
      zoomAnchorRef.current = {
        pageNumber: displayedPage,
        relativeOffset: Math.max(0, Math.min(1, (viewport.scrollTop - pageTop) / page.offsetHeight)),
      };
    }
    if (highlightText) {
      setHighlightResult({ requestId: highlightRequestId, status: "locating" });
    }
    setZoom((current) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, current + delta)));
  }

  function retryLoad() {
    setLoadError(false);
    setFileSource(null);
    setReloadKey((key) => key + 1);
  }

  return (
    <section
      className="workspace-pdf-highlight"
      style={{
        flex: "6 1 480px",
        minWidth: 0,
        display: hidden ? "none" : "flex",
        flexDirection: "column",
        borderRight: "1px solid var(--l-line)",
        background: "#EFEADF",
        minHeight: 0,
      }}
    >
      <div
        style={{
          flex: "none",
          display: "flex",
          flexWrap: "wrap",
          gap: 12,
          alignItems: "center",
          justifyContent: "space-between",
          padding: "10px 20px",
          borderBottom: "1px solid var(--l-line)",
          background: "var(--l-paper)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          <IconButton disabled={displayedPage <= 1 || loadError} onClick={() => requestPage(displayedPage - 1)} label="Previous page">
            &#8249;
          </IconButton>
          <span aria-live="polite" style={{ fontFamily: "var(--font-mono-editorial)", fontSize: 11.5, color: "var(--l-muted)", whiteSpace: "nowrap" }}>
            {numPages ? `Page ${displayedPage} of ${numPages}` : "Loading"}
          </span>
          <IconButton disabled={!numPages || displayedPage >= numPages || loadError} onClick={() => requestPage(displayedPage + 1)} label="Next page">
            &#8250;
          </IconButton>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <IconButton disabled={loadError || zoom <= MIN_ZOOM} onClick={() => changeZoom(-ZOOM_STEP)} label="Zoom out">
            &#8722;
          </IconButton>
          <span style={{ fontFamily: "var(--font-mono-editorial)", fontSize: 11.5, color: "var(--l-muted)", width: 44, textAlign: "center" }}>
            {zoom}%
          </span>
          <IconButton disabled={loadError || zoom >= MAX_ZOOM} onClick={() => changeZoom(ZOOM_STEP)} label="Zoom in">
            &#43;
          </IconButton>
        </div>
      </div>

      {highlightText && !loadError && (
        <div
          style={{
            flex: "none",
            display: "flex",
            flexWrap: "wrap",
            gap: 10,
            alignItems: "baseline",
            justifyContent: "space-between",
            padding: "8px 20px",
            borderBottom: "1px solid rgba(154,91,60,0.3)",
            background: "rgba(154,91,60,0.08)",
          }}
        >
          <span style={{ fontFamily: "var(--font-mono-editorial)", fontSize: 10.5, color: "var(--l-text)", minWidth: 0 }}>
            Showing the source for: <span style={{ color: ACCENT }}>{highlightQuestion}</span>
          </span>
          <span
            role="status"
            data-testid="citation-highlight-status"
            style={{
              marginLeft: "auto",
              fontFamily: "var(--font-mono-editorial)",
              fontSize: 10.5,
              color: highlightStatus === "not-found" ? "#7A3E2A" : "var(--l-muted)",
              whiteSpace: "nowrap",
            }}
          >
            {highlightStatus === "visible"
              ? "Passage highlighted"
              : highlightStatus === "not-found"
                ? `Exact passage not found. Showing page ${highlightPageNumber}.`
                : "Locating passage"}
          </span>
          <button
            type="button"
            onClick={onClearHighlight}
            style={{
              cursor: "pointer",
              fontFamily: "var(--font-mono-editorial)",
              fontSize: 10.5,
              background: "transparent",
              border: 0,
              padding: 0,
              color: "var(--l-muted)",
              whiteSpace: "nowrap",
            }}
          >
            Clear highlight
          </button>
        </div>
      )}

      <div ref={viewportRef} data-testid="pdf-scroll-viewport" style={{ flex: "1 1 auto", minHeight: 0, overflow: "auto", padding: "20px 20px 32px", scrollBehavior: "auto" }}>
        {loadError ? (
          <PdfLoadError onRetry={retryLoad} />
        ) : !readyFileSource || !pageWidth ? (
          <PdfLoadingSkeleton />
        ) : (
          <Document
            key={reloadKey}
            file={readyFileSource}
            loading={<PdfLoadingSkeleton />}
            onLoadSuccess={handleLoadSuccess}
            onLoadError={() => setLoadError(true)}
            onSourceError={() => setLoadError(true)}
            error={<div />}
          >
            <div style={{ width: pageWidth, minWidth: pageWidth, margin: "0 auto" }}>
              {Array.from({ length: numPages }, (_, index) => {
                const pageNumber = index + 1;
                const estimatedHeight = estimatePdfPageHeight(pageWidth, pageAspectRatios[pageNumber]);
                return (
                  <VirtualPdfPage
                    key={pageNumber}
                    pageNumber={pageNumber}
                    pageWidth={pageWidth}
                    estimatedHeight={estimatedHeight}
                    rendered={renderedPages.has(pageNumber)}
                    renderTextLayer={Boolean(highlightText) && highlightPageNumber === pageNumber}
                    onPageElement={setPageElement}
                    onPageLoad={handlePageLoad}
                    onTextLayerRendered={handleTextLayerRendered}
                    onTextLayerError={handleTextLayerError}
                  />
                );
              })}
            </div>
          </Document>
        )}
      </div>
    </section>
  );
}

const VirtualPdfPage = memo(function VirtualPdfPage({
  pageNumber,
  pageWidth,
  estimatedHeight,
  rendered,
  renderTextLayer,
  onPageElement,
  onPageLoad,
  onTextLayerRendered,
  onTextLayerError,
}: {
  pageNumber: number;
  pageWidth: number;
  estimatedHeight: number;
  rendered: boolean;
  renderTextLayer: boolean;
  onPageElement: (pageNumber: number, element: HTMLDivElement | null) => void;
  onPageLoad: (page: LoadedPdfPage) => void;
  onTextLayerRendered: (pageNumber: number) => void;
  onTextLayerError: (pageNumber: number) => void;
}) {
  const registerElement = useCallback(
    (element: HTMLDivElement | null) => onPageElement(pageNumber, element),
    [onPageElement, pageNumber],
  );
  const handleTextLayerRendered = useCallback(
    () => onTextLayerRendered(pageNumber),
    [onTextLayerRendered, pageNumber],
  );
  const handleTextLayerError = useCallback(
    () => onTextLayerError(pageNumber),
    [onTextLayerError, pageNumber],
  );

  return (
    <div
      ref={registerElement}
      data-pdf-page={pageNumber}
      style={{
        position: "relative",
        width: pageWidth,
        minHeight: estimatedHeight,
        marginBottom: PAGE_GAP,
        scrollMarginTop: 12,
      }}
    >
      {rendered ? (
        <div
          style={{
            width: pageWidth,
            minHeight: estimatedHeight,
            overflow: "hidden",
            background: "var(--l-surface-alt)",
            border: "1px solid #DFD8CB",
            borderRadius: 2,
            boxShadow: "0 1px 0 rgba(27,26,23,0.04), 0 24px 44px -40px rgba(27,26,23,0.55)",
          }}
        >
          <Page
            pageNumber={pageNumber}
            width={pageWidth}
            renderAnnotationLayer={false}
            renderTextLayer={renderTextLayer}
            onLoadSuccess={onPageLoad}
            onRenderTextLayerSuccess={handleTextLayerRendered}
            onRenderTextLayerError={handleTextLayerError}
            loading={<PdfPagePlaceholder pageNumber={pageNumber} height={estimatedHeight} />}
          />
        </div>
      ) : (
        <PdfPagePlaceholder pageNumber={pageNumber} height={estimatedHeight} />
      )}
      {rendered && (
        <div
          data-citation-highlight-layer
          aria-hidden="true"
          style={{ position: "absolute", inset: 0, overflow: "hidden", pointerEvents: "none", zIndex: 3 }}
        />
      )}
    </div>
  );
});

function PdfPagePlaceholder({ pageNumber, height }: { pageNumber: number; height: number }) {
  return (
    <div
      aria-label={`Page ${pageNumber}`}
      style={{
        width: "100%",
        height,
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "flex-end",
        padding: 12,
        background: "var(--l-surface-alt)",
        border: "1px solid #DFD8CB",
        borderRadius: 2,
        color: "var(--l-faint)",
        fontFamily: "var(--font-mono-editorial)",
        fontSize: 9.5,
      }}
    >
      {pageNumber}
    </div>
  );
}

function PdfLoadError({ onRetry }: { onRetry: () => void }) {
  return (
    <div style={{ maxWidth: 520, margin: "44px auto 0" }}>
      <h2 style={{ fontFamily: "var(--font-serif-display)", fontWeight: 400, fontSize: 27, lineHeight: 1.14, margin: 0 }}>
        We could not open this PDF.
      </h2>
      <p style={{ margin: "12px 0 0", fontSize: 14.5, lineHeight: 1.6, color: "var(--l-text)" }}>
        The file did not load. Try opening it again. If it still will not open, upload the lease again from your documents.
      </p>
      <div style={{ marginTop: 20, display: "flex", flexWrap: "wrap", gap: 12 }}>
        <button
          type="button"
          onClick={onRetry}
          style={{
            cursor: "pointer",
            fontFamily: "var(--font-sans-editorial)",
            display: "inline-flex",
            alignItems: "center",
            height: 38,
            padding: "0 18px",
            background: "var(--l-ink)",
            color: "var(--l-surface)",
            border: "1px solid var(--l-ink)",
            borderRadius: 2,
            fontSize: 13.5,
          }}
        >
          Try opening again
        </button>
      </div>
    </div>
  );
}

function IconButton({
  children,
  onClick,
  disabled,
  label,
}: {
  children: ReactNode;
  onClick: () => void;
  disabled: boolean;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      style={{
        cursor: disabled ? "not-allowed" : "pointer",
        fontFamily: "var(--font-mono-editorial)",
        width: 30,
        height: 30,
        border: "1px solid var(--l-line-strong)",
        background: "var(--l-surface)",
        borderRadius: 2,
        color: "var(--l-text)",
        fontSize: 13,
        opacity: disabled ? 0.45 : 1,
      }}
    >
      {children}
    </button>
  );
}

function PdfLoadingSkeleton() {
  return (
    <div style={{ maxWidth: 640, margin: "0 auto", background: "var(--l-surface-alt)", border: "1px solid #DFD8CB", borderRadius: 2, padding: "44px 46px" }}>
      <div style={{ fontFamily: "var(--font-mono-editorial)", fontSize: 11, color: "var(--l-muted)", display: "flex", alignItems: "center", gap: 9 }}>
        <span style={{ display: "block", width: 70, height: 3, background: "#E6E0D5", borderRadius: 2, overflow: "hidden", position: "relative" }}>
          <span style={{ position: "absolute", inset: 0, width: "30%", background: ACCENT, animation: "kylSlide 1.7s ease-in-out infinite" }} />
        </span>
        Loading your document
      </div>
      <div style={{ marginTop: 28, display: "flex", flexDirection: "column", gap: 9 }}>
        <span style={{ height: 6, borderRadius: 1, background: "#EDE7DC", width: "100%", display: "block" }} />
        <span style={{ height: 6, borderRadius: 1, background: "#EDE7DC", width: "94%", display: "block" }} />
        <span style={{ height: 6, borderRadius: 1, background: "#EDE7DC", width: "97%", display: "block" }} />
        <span style={{ height: 6, borderRadius: 1, background: "#EDE7DC", width: "58%", display: "block" }} />
        <span style={{ height: 6, borderRadius: 1, background: "#F1ECE3", width: "88%", marginTop: 16, display: "block" }} />
        <span style={{ height: 6, borderRadius: 1, background: "#F1ECE3", width: "92%", display: "block" }} />
        <span style={{ height: 6, borderRadius: 1, background: "#F1ECE3", width: "46%", display: "block" }} />
      </div>
    </div>
  );
}
