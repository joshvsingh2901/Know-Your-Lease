import type { AnswerCitation } from "@/types/document";

export interface ThreadEntry {
  id: number;
  question: string;
  status: "loading" | "answered" | "error";
  answer: string;
  citations: AnswerCitation[];
  cached: boolean;
  errorMessage: string | null;
}

function normalizeQuestion(question: string): string {
  return question.trim().toLowerCase();
}

/** An exact-match (normalized) prior answered question in this session's thread --
 * mirrors the backend's own exact-question answer cache, so reusing it locally is an
 * accurate shortcut rather than a fabricated behavior. A "loading" or "error" entry
 * for the same text never counts, since it never resolved to a real answer. */
export function findAnsweredEntry(thread: ThreadEntry[], question: string): ThreadEntry | undefined {
  const normalized = normalizeQuestion(question);
  return thread.find((entry) => entry.status === "answered" && normalizeQuestion(entry.question) === normalized);
}

/** The question text of the most recent thread entry whose citations include the
 * given citation id, used to label the "Showing the source for" banner above the PDF
 * when a citation is opened. Returns null when no citation is active or none match. */
export function findHighlightQuestion(thread: ThreadEntry[], activeCitationId: string | null): string | null {
  if (!activeCitationId) return null;
  for (let index = thread.length - 1; index >= 0; index -= 1) {
    const entry = thread[index];
    if (entry.citations.some((citation) => citation.chunk_id === activeCitationId)) {
      return entry.question;
    }
  }
  return null;
}

export function formatCitationExcerpt(snippet: string, maxLength = 180): string {
  const normalized = snippet.replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) return normalized;

  const candidate = normalized.slice(0, Math.max(1, maxLength - 1));
  const wordBoundary = candidate.lastIndexOf(" ");
  const cutoff = wordBoundary >= Math.floor(maxLength * 0.65) ? wordBoundary : candidate.length;
  return `${candidate.slice(0, cutoff).trimEnd()}…`;
}
