import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const {
  clampPdfPage,
  estimatePdfPageHeight,
  getAnchoredScrollTop,
  getCurrentPageFromViewport,
  getPassageScrollTop,
  getRenderedPageNumbers,
} = await import("../components/workspace/pdf-viewer-utils.ts");

test("continuous scrolling reports the page at the viewport reading line", () => {
  const pages = [
    { pageNumber: 1, top: 0, bottom: 800 },
    { pageNumber: 2, top: 818, bottom: 1618 },
    { pageNumber: 3, top: 1636, bottom: 2436 },
  ];

  assert.equal(getCurrentPageFromViewport(pages, 0, 600), 1);
  assert.equal(getCurrentPageFromViewport(pages, 800, 600), 2);
  assert.equal(getCurrentPageFromViewport(pages, 1618, 600), 3);
});

test("the viewer bounds expensive page rendering around the current page", () => {
  assert.deepEqual(getRenderedPageNumbers(12, 24, null), [10, 11, 12, 13, 14]);
  assert.deepEqual(getRenderedPageNumbers(1, 24, null), [1, 2, 3]);
  assert.deepEqual(getRenderedPageNumbers(24, 24, null), [22, 23, 24]);
  assert.deepEqual(getRenderedPageNumbers(12, 24, 2), [2, 10, 11, 12, 13, 14]);
});

test("page controls clamp to the real PDF bounds", () => {
  assert.equal(clampPdfPage(0, 24), 1);
  assert.equal(clampPdfPage(25, 24), 24);
  assert.equal(clampPdfPage(9, 24), 9);
});

test("zoom keeps the same relative reading position and page aspect ratio", () => {
  assert.equal(getAnchoredScrollTop(1000, 1200, 0.25), 1300);
  assert.equal(getAnchoredScrollTop(1000, 1200, 2), 2200);
  assert.equal(estimatePdfPageHeight(850), 1100);
});

test("a located passage scrolls within the PDF viewport to a comfortable reading position", () => {
  assert.equal(getPassageScrollTop(1200, 100, 800, 650), 1570);
  assert.equal(getPassageScrollTop(0, 100, 800, 120), 0);
});

test("zoom does not key or recreate the authenticated PDF document", () => {
  const source = readFileSync(
    fileURLToPath(new URL("../components/workspace/workspace-pdf-pane-client.tsx", import.meta.url)),
    "utf8",
  );

  assert.match(source, /<Document\s+[\s\S]*?key=\{reloadKey\}/);
  assert.equal(source.includes("key={zoom}"), false);
  assert.match(source, /\}, \[documentId, reloadKey\]\);/);
});

test("citation selection carries the real page and snippet into the viewer", () => {
  const source = readFileSync(
    fileURLToPath(new URL("../components/workspace/workspace-shell.tsx", import.meta.url)),
    "utf8",
  );

  assert.match(source, /setActiveCitation\(citation\)/);
  assert.match(source, /setHighlightRequestId\(\(requestId\) => requestId \+ 1\)/);
  assert.match(source, /setCurrentPage\(citation\.page_number\)/);
  assert.match(source, /highlightText=\{activeCitation\?\.snippet \?\? null\}/);
  assert.match(source, /highlightPageNumber=\{activeCitation\?\.page_number \?\? null\}/);
});

test("text-layer completion reapplies highlights after zoom or a retained-page render", () => {
  const source = readFileSync(
    fileURLToPath(new URL("../components/workspace/workspace-pdf-pane-client.tsx", import.meta.url)),
    "utf8",
  );

  assert.match(source, /onRenderTextLayerSuccess=\{handleTextLayerRendered\}/);
  assert.match(source, /textLayerRender\.revision/);
  assert.match(source, /status: "locating"/);
  assert.match(source, /status: "visible"/);
  assert.match(source, /status: "not-found"/);
  assert.match(source, /Exact passage not found\. Showing page/);
});
