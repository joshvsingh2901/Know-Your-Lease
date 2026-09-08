const HIGHLIGHT_ATTRIBUTE = "data-citation-highlight";
const HIGHLIGHT_LAYER_SELECTOR = "[data-citation-highlight-layer]";
const HIGHLIGHT_OVERLAY_ATTRIBUTE = "data-citation-highlight-overlay";
const TEXT_SPAN_SELECTOR = ".react-pdf__Page__textContent span";

interface SourceCharacterOffset {
  start: number;
  end: number;
}

interface TextSpanRange {
  element: HTMLSpanElement;
  start: number;
  end: number;
  sourceOffsets: SourceCharacterOffset[];
}

interface TextMatch {
  start: number;
  end: number;
}

export interface HighlightRectangle {
  left: number;
  top: number;
  width: number;
  height: number;
}

export function normalizePdfText(value: string): string {
  return value
    .normalize("NFKC")
    .replace(/\u00ad/g, "")
    .replace(/[\p{P}\p{S}\s]+/gu, "")
    .toLowerCase();
}

function normalizePdfTextWithOffsets(value: string): {
  text: string;
  sourceOffsets: SourceCharacterOffset[];
} {
  let text = "";
  const sourceOffsets: SourceCharacterOffset[] = [];
  let sourceIndex = 0;

  for (const character of value) {
    const sourceEnd = sourceIndex + character.length;
    const normalizedCharacter = normalizePdfText(character);
    text += normalizedCharacter;
    for (let index = 0; index < normalizedCharacter.length; index += 1) {
      sourceOffsets.push({ start: sourceIndex, end: sourceEnd });
    }
    sourceIndex = sourceEnd;
  }

  return { text, sourceOffsets };
}

export function clearCitationHighlight(root: HTMLElement): void {
  root.querySelectorAll<HTMLSpanElement>(`span[${HIGHLIGHT_ATTRIBUTE}]`).forEach((span) => {
    span.removeAttribute(HIGHLIGHT_ATTRIBUTE);
  });
  root.querySelector<HTMLElement>(HIGHLIGHT_LAYER_SELECTOR)?.replaceChildren();
}

function findTextMatch(combinedText: string, snippet: string): TextMatch | null {
  const target = normalizePdfText(snippet);
  if (target.length < 12) return null;

  const exactStart = combinedText.indexOf(target);
  if (exactStart >= 0 && combinedText.indexOf(target, exactStart + 1) < 0) {
    return { start: exactStart, end: exactStart + target.length };
  }

  const words = snippet
    .normalize("NFKC")
    .replace(/\u00ad/g, "")
    .match(/[\p{L}\p{N}]+/gu)
    ?.map((word) => word.toLowerCase()) ?? [];

  // PyMuPDF and PDF.js occasionally disagree by one extracted word. Removing one
  // source word still gives us a long, precise passage without trusting a short,
  // generic phrase such as "the tenant agrees to".
  if (words.length >= 6) {
    for (let omittedIndex = 0; omittedIndex < words.length; omittedIndex += 1) {
      const candidate = words.filter((_, index) => index !== omittedIndex).join("");
      if (candidate.length < 24) continue;
      const candidateStart = combinedText.indexOf(candidate);
      if (candidateStart >= 0 && combinedText.indexOf(candidate, candidateStart + 1) < 0) {
        return { start: candidateStart, end: candidateStart + candidate.length };
      }
    }
  }

  // A bounded unique anchor is the final text-only fallback. Six words and 24
  // normalized characters, covering most of the excerpt, deliberately reject
  // coincidental short phrase matches.
  for (let windowSize = Math.min(12, words.length); windowSize >= 6; windowSize -= 1) {
    for (let index = 0; index <= words.length - windowSize; index += 1) {
      const anchor = words.slice(index, index + windowSize).join("");
      if (anchor.length < Math.max(24, Math.ceil(target.length * 0.6))) continue;
      const anchorStart = combinedText.indexOf(anchor);
      if (anchorStart >= 0 && combinedText.indexOf(anchor, anchorStart + 1) < 0) {
        return { start: anchorStart, end: anchorStart + anchor.length };
      }
    }
  }
  return null;
}

function isRenderedTextSpan(element: HTMLSpanElement): boolean {
  // Tagged PDFs wrap real text spans in `span.markedContent`. Those wrappers have
  // zero height and repeat all descendant text. Including them corrupts the combined
  // string and can also create a technically marked but invisible highlight.
  return !element.classList.contains("markedContent") && element.querySelector("span") === null;
}

function isSameVisualLine(left: HighlightRectangle, right: HighlightRectangle): boolean {
  const overlap =
    Math.min(left.top + left.height, right.top + right.height) - Math.max(left.top, right.top);
  return overlap >= Math.min(left.height, right.height) * 0.55;
}

/** Coalesces adjacent matched glyph runs without changing what text matched. Large
 * horizontal gaps remain separate, while normal inter-word gaps become one familiar
 * PDF-annotation rectangle per visual line. */
export function mergeHighlightRectangles(
  rectangles: HighlightRectangle[],
): HighlightRectangle[] {
  const lines: HighlightRectangle[][] = [];
  const sorted = [...rectangles].sort((left, right) => left.top - right.top || left.left - right.left);

  for (const rectangle of sorted) {
    const line = lines.find((candidate) => candidate.some((item) => isSameVisualLine(item, rectangle)));
    if (line) line.push(rectangle);
    else lines.push([rectangle]);
  }

  return lines.flatMap((line) => {
    const runs: HighlightRectangle[] = [];
    for (const rectangle of line.sort((left, right) => left.left - right.left)) {
      const previous = runs.at(-1);
      if (!previous) {
        runs.push({ ...rectangle });
        continue;
      }

      const gap = rectangle.left - (previous.left + previous.width);
      const maximumWordGap = Math.max(5, Math.min(previous.height, rectangle.height) * 0.75);
      if (gap > maximumWordGap) {
        runs.push({ ...rectangle });
        continue;
      }

      const right = Math.max(previous.left + previous.width, rectangle.left + rectangle.width);
      const bottom = Math.max(previous.top + previous.height, rectangle.top + rectangle.height);
      previous.left = Math.min(previous.left, rectangle.left);
      previous.top = Math.min(previous.top, rectangle.top);
      previous.width = right - previous.left;
      previous.height = bottom - previous.top;
    }
    return runs;
  });
}

function renderHighlightOverlays(
  root: HTMLElement,
  ranges: TextSpanRange[],
  match: TextMatch,
): number | null {
  const layer = root.querySelector<HTMLElement>(HIGHLIGHT_LAYER_SELECTOR);
  if (!layer) return null;

  const layerRect = layer.getBoundingClientRect();
  const rectangles: HighlightRectangle[] = [];
  for (const range of ranges) {
    if (range.start >= match.end || range.end <= match.start) continue;

    const textNode = [...range.element.childNodes].find((node) => node.nodeType === 3);
    if (!textNode) continue;
    const localStart = Math.max(match.start, range.start) - range.start;
    const localEnd = Math.min(match.end, range.end) - range.start;
    const sourceStart = range.sourceOffsets[localStart]?.start;
    const sourceEnd = range.sourceOffsets[localEnd - 1]?.end;
    if (sourceStart === undefined || sourceEnd === undefined || sourceEnd <= sourceStart) continue;

    const selection = range.element.ownerDocument.createRange();
    selection.setStart(textNode, sourceStart);
    selection.setEnd(textNode, sourceEnd);
    for (const rect of selection.getClientRects()) {
      if (rect.width <= 1 || rect.height <= 1) continue;
      rectangles.push({
        left: rect.left - layerRect.left,
        top: rect.top - layerRect.top,
        width: rect.width,
        height: rect.height,
      });
    }
  }

  const mergedRectangles = mergeHighlightRectangles(rectangles);
  for (const rectangle of mergedRectangles) {
    const overlay = layer.ownerDocument.createElement("span");
    overlay.setAttribute(HIGHLIGHT_OVERLAY_ATTRIBUTE, "true");
    overlay.style.left = `${rectangle.left}px`;
    overlay.style.top = `${rectangle.top}px`;
    overlay.style.width = `${rectangle.width}px`;
    overlay.style.height = `${rectangle.height}px`;
    layer.append(overlay);
  }
  return mergedRectangles.length;
}

export function highlightCitationSnippet(root: HTMLElement, snippet: string): boolean {
  clearCitationHighlight(root);

  const ranges: TextSpanRange[] = [];
  let combinedText = "";
  root.querySelectorAll<HTMLSpanElement>(TEXT_SPAN_SELECTOR).forEach((element) => {
    if (!isRenderedTextSpan(element)) return;
    const { text, sourceOffsets } = normalizePdfTextWithOffsets(element.textContent ?? "");
    if (!text) return;
    const start = combinedText.length;
    combinedText += text;
    ranges.push({ element, start, end: combinedText.length, sourceOffsets });
  });

  const match = findTextMatch(combinedText, snippet);
  if (!match) return false;
  for (const range of ranges) {
    if (range.start < match.end && range.end > match.start) {
      range.element.setAttribute(HIGHLIGHT_ATTRIBUTE, "true");
    }
  }
  const overlayCount = renderHighlightOverlays(root, ranges, match);
  if (overlayCount === 0) {
    clearCitationHighlight(root);
    return false;
  }
  return true;
}
