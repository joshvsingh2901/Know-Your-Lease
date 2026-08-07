"use client";

import { FormEvent, useState } from "react";

import { ApiError, askDocumentQuestion } from "@/lib/api";
import type { AnswerCitation, QuestionAnswer } from "@/types/document";

const QUESTION_SUGGESTIONS = [
  "Can I have pets?",
  "What extra fees should I know about?",
  "Can I sublet?",
  "When can the landlord enter?",
  "What happens if I end the lease early?",
];

interface QuestionPanelProps {
  documentId: string;
  activeCitationId: string | null;
  onCitationSelect: (citation: AnswerCitation) => void;
}

export function QuestionPanel({
  documentId,
  activeCitationId,
  onCitationSelect,
}: QuestionPanelProps) {
  const [question, setQuestion] = useState("");
  const [isAsking, setIsAsking] = useState(false);
  const [result, setResult] = useState<QuestionAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || isAsking) return;

    setIsAsking(true);
    setError(null);
    setResult(null);
    try {
      setResult(await askDocumentQuestion(documentId, trimmedQuestion));
    } catch (questionError) {
      setError(
        questionError instanceof ApiError
          ? questionError.message
          : "Your question could not be answered. Please try again.",
      );
    } finally {
      setIsAsking(false);
    }
  }

  return (
    <section
      className="mt-5 overflow-hidden rounded-2xl border border-[var(--line)] bg-white shadow-[0_18px_60px_rgba(19,43,58,0.08)]"
      aria-labelledby="question-heading"
    >
      <div className="border-b border-[var(--line)] px-5 py-5 sm:px-7">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--success)]">
          Your lease is ready
        </p>
        <h2 id="question-heading" className="mt-1 font-serif text-2xl text-[var(--navy)]">
          Ask about your lease
        </h2>
        <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
          Answers use only the indexed lease excerpts and include the supporting sources.
        </p>
      </div>

      <div className="p-5 sm:p-7">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
            Try a question
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {QUESTION_SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => {
                  setQuestion(suggestion);
                  setError(null);
                }}
                disabled={isAsking}
                className="rounded-full border border-[var(--line)] bg-[var(--paper)] px-3 py-2 text-left text-xs font-medium text-[var(--navy)] transition-colors hover:border-[var(--accent)] hover:text-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>

        <form onSubmit={submitQuestion} className="mt-5">
          <label htmlFor="lease-question" className="sr-only">
            Question about your lease
          </label>
          <textarea
            id="lease-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            disabled={isAsking}
            maxLength={1000}
            rows={4}
            placeholder="What fees should I know about?"
            className="block w-full resize-y rounded-xl border border-[#c8cbc7] bg-white px-4 py-3 text-sm leading-6 text-[var(--ink)] shadow-inner outline-none transition-colors placeholder:text-[#879198] focus:border-[var(--accent)] disabled:cursor-wait disabled:bg-[#f5f5f2]"
          />
          <div className="mt-3 flex items-center justify-between gap-4">
            <p className="text-xs text-[var(--muted)]">Each question is answered independently.</p>
            <button
              type="submit"
              disabled={isAsking || !question.trim()}
              className="inline-flex min-w-24 items-center justify-center gap-2 rounded-lg bg-[var(--accent)] px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[var(--accent-dark)] disabled:cursor-not-allowed disabled:opacity-55"
            >
              {isAsking && (
                <span
                  className="size-4 animate-spin rounded-full border-2 border-white/35 border-t-white"
                  aria-hidden="true"
                />
              )}
              {isAsking ? "Asking…" : "Ask"}
            </button>
          </div>
        </form>

        <div aria-live="polite">
          {isAsking && (
            <p className="mt-5 rounded-xl border border-[#c9d3d8] bg-[#f1f5f6] px-4 py-3 text-sm text-[var(--navy)]">
              Finding the relevant clauses and preparing a grounded answer…
            </p>
          )}
          {error && (
            <p
              role="alert"
              className="mt-5 rounded-xl border border-[#ebc4bf] bg-[var(--error-bg)] px-4 py-3 text-sm text-[var(--error)]"
            >
              {error}
            </p>
          )}
        </div>

        {result && (
          <div className="mt-7 border-t border-[var(--line)] pt-6">
            <h3 className="text-xs font-semibold uppercase tracking-[0.15em] text-[var(--accent)]">
              Answer
            </h3>
            <p className="mt-3 whitespace-pre-wrap text-base leading-7 text-[var(--ink)]">
              {result.answer}
            </p>

            {result.citations.length > 0 && (
              <div className="mt-7">
                <h3 className="font-semibold text-[var(--navy)]">Sources</h3>
                <div className="mt-3 space-y-3">
                  {result.citations.map((citation) => (
                    <article
                      key={citation.chunk_id}
                      className={`rounded-xl border p-4 transition-colors ${
                        activeCitationId === citation.chunk_id
                          ? "border-[var(--accent)] bg-[#fbf6f2] ring-1 ring-[var(--accent)]"
                          : "border-[var(--line)] bg-[var(--paper)]"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-4 text-sm font-semibold text-[var(--navy)]">
                        <span>
                          Page {citation.page_number}
                          {citation.section_title ? ` · ${citation.section_title}` : ""}
                        </span>
                      </div>
                      <p className="mt-3 text-sm leading-6 text-[var(--muted)]">{citation.snippet}</p>
                      <div className="mt-4 border-t border-[var(--line)] pt-3">
                        <button
                          type="button"
                          onClick={() => onCitationSelect(citation)}
                          className="text-sm font-semibold text-[var(--accent)] underline underline-offset-4"
                        >
                          View in lease
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
