export const PDF_RENDER_RADIUS = 2;

export interface PageViewportMetric {
  pageNumber: number;
  top: number;
  bottom: number;
}

export function clampPdfPage(pageNumber: number, numPages: number): number {
  if (numPages < 1) return Math.max(1, pageNumber);
  return Math.min(Math.max(pageNumber, 1), numPages);
}

/** Keeps canvas and text-layer work bounded while every page retains a lightweight
 * layout placeholder for natural document scrolling. The cited page is retained so
 * its real text highlight survives if the reader briefly scrolls elsewhere. */
export function getRenderedPageNumbers(
  currentPage: number,
  numPages: number,
  highlightedPage: number | null,
  radius = PDF_RENDER_RADIUS,
): number[] {
  if (numPages < 1) return [];

  const center = clampPdfPage(currentPage, numPages);
  const pages = new Set<number>();
  for (let page = Math.max(1, center - radius); page <= Math.min(numPages, center + radius); page += 1) {
    pages.add(page);
  }
  if (highlightedPage !== null) pages.add(clampPdfPage(highlightedPage, numPages));
  return [...pages].sort((left, right) => left - right);
}

/** Selects the page occupying the reading line near the upper third of the viewport.
 * Falling back to the closest page center keeps the indicator stable in page gaps. */
export function getCurrentPageFromViewport(
  pages: PageViewportMetric[],
  viewportTop: number,
  viewportHeight: number,
): number | null {
  if (pages.length === 0) return null;

  const readingLine = viewportTop + viewportHeight * 0.34;
  const containing = pages.find((page) => page.top <= readingLine && page.bottom >= readingLine);
  if (containing) return containing.pageNumber;

  let closest = pages[0];
  let closestDistance = Math.abs((closest.top + closest.bottom) / 2 - readingLine);
  for (const page of pages.slice(1)) {
    const distance = Math.abs((page.top + page.bottom) / 2 - readingLine);
    if (distance < closestDistance) {
      closest = page;
      closestDistance = distance;
    }
  }
  return closest.pageNumber;
}

export function estimatePdfPageHeight(pageWidth: number, aspectRatio = 11 / 8.5): number {
  return Math.max(1, Math.round(pageWidth * aspectRatio));
}

export function getAnchoredScrollTop(
  pageTop: number,
  pageHeight: number,
  relativeOffset: number,
): number {
  return pageTop + pageHeight * Math.max(0, Math.min(1, relativeOffset));
}

/** Positions the located passage below the toolbar without asking scrollIntoView to
 * move unrelated ancestors, which keeps the answer pane exactly where the reader left it. */
export function getPassageScrollTop(
  currentScrollTop: number,
  viewportTop: number,
  viewportHeight: number,
  passageTop: number,
): number {
  const comfortableOffset = Math.min(180, Math.max(72, viewportHeight * 0.24));
  return Math.max(0, currentScrollTop + passageTop - viewportTop - comfortableOffset);
}
