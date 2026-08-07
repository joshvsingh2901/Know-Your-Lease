const HIGHLIGHT_ATTRIBUTE = "data-citation-highlight";
const TEXT_SPAN_SELECTOR = ".react-pdf__Page__textContent span";

interface TextSpanRange {
  element: HTMLSpanElement;
  start: number;
  end: number;
}

export function normalizePdfText(value: string): string {
  return value
    .normalize("NFKC")
    .replace(/\u00ad/g, "")
    .replace(/\s+/g, "")
    .toLocaleLowerCase();
}

export function clearCitationHighlight(root: HTMLElement): void {
  root.querySelectorAll<HTMLSpanElement>(`span[${HIGHLIGHT_ATTRIBUTE}]`).forEach((span) => {
    span.removeAttribute(HIGHLIGHT_ATTRIBUTE);
  });
}

export function highlightCitationSnippet(root: HTMLElement, snippet: string): boolean {
  clearCitationHighlight(root);

  const target = normalizePdfText(snippet);
  if (target.length < 12) return false;

  const ranges: TextSpanRange[] = [];
  let combinedText = "";
  root.querySelectorAll<HTMLSpanElement>(TEXT_SPAN_SELECTOR).forEach((element) => {
    const text = normalizePdfText(element.textContent ?? "");
    if (!text) return;
    const start = combinedText.length;
    combinedText += text;
    ranges.push({ element, start, end: combinedText.length });
  });

  const matchStart = combinedText.indexOf(target);
  if (matchStart < 0) return false;
  const matchEnd = matchStart + target.length;
  for (const range of ranges) {
    if (range.start < matchEnd && range.end > matchStart) {
      range.element.setAttribute(HIGHLIGHT_ATTRIBUTE, "true");
    }
  }
  return true;
}
