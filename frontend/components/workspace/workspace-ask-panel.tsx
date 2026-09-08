"use client";

import { FormEvent } from "react";

import type { ThreadEntry } from "./use-question-thread";
import type { AnswerCitation } from "@/types/document";
import { AnswerMarkdown } from "./answer-markdown";
import { formatCitationExcerpt } from "./thread-utils";

const ACCENT = "var(--l-accent)";

const SUGGESTIONS = ["Can I have pets?", "Can I leave early?", "When is rent due?", "Who handles repairs?"];

interface WorkspaceAskPanelProps {
  thread: ThreadEntry[];
  draft: string;
  onDraftChange: (value: string) => void;
  onAsk: (question: string) => void;
  activeCitationId: string | null;
  onViewCitation: (citation: AnswerCitation, question: string) => void;
  hidden?: boolean;
}

export function WorkspaceAskPanel({
  thread,
  draft,
  onDraftChange,
  onAsk,
  activeCitationId,
  onViewCitation,
  hidden = false,
}: WorkspaceAskPanelProps) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = draft.trim();
    if (!question) return;
    onDraftChange("");
    onAsk(question);
  }

  return (
    <section
      style={{
        flex: "4 1 380px",
        minWidth: 0,
        maxWidth: 600,
        display: hidden ? "none" : "flex",
        flexDirection: "column",
        background: "var(--l-paper)",
        minHeight: 0,
      }}
    >
      <div
        style={{
          flex: "none",
          padding: "14px 22px 12px",
          borderBottom: "1px solid var(--l-line)",
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: 12,
        }}
      >
        <span style={{ fontFamily: "var(--font-serif-display)", fontSize: 19 }}>Ask about this lease</span>
        <span style={{ fontFamily: "var(--font-mono-editorial)", fontSize: 10.5, color: "var(--l-muted)", whiteSpace: "nowrap" }}>
          {thread.length === 0 ? "" : thread.length === 1 ? "1 question" : `${thread.length} questions`}
        </span>
      </div>

      <div style={{ flex: "1 1 auto", minHeight: 0, overflow: "auto", padding: "18px 22px 26px", display: "flex", flexDirection: "column", gap: 22 }}>
        {thread.length === 0 && (
          <div>
            <h2 style={{ margin: 0, fontFamily: "var(--font-serif-display)", fontWeight: 400, fontSize: 30, lineHeight: 1.1, letterSpacing: "-0.01em" }}>
              What would you like to understand?
            </h2>
            <p style={{ margin: "11px 0 0", fontSize: 14.5, lineHeight: 1.6, color: "var(--l-text)" }}>
              Ask in your own words. Every answer comes from the lease you uploaded, and each one shows the clause it
              came from so you can read it yourself.
            </p>
            <div
              style={{
                margin: "22px 0 0",
                fontFamily: "var(--font-mono-editorial)",
                fontSize: 10.5,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                color: "var(--l-muted)",
              }}
            >
              Start with a common question
            </div>
            <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 7 }}>
              {SUGGESTIONS.map((text) => (
                <button
                  key={text}
                  className="lease-question-suggestion"
                  type="button"
                  onClick={() => onAsk(text)}
                  style={{
                    cursor: "pointer",
                    textAlign: "left",
                    display: "flex",
                    alignItems: "baseline",
                    gap: 12,
                    fontFamily: "var(--font-serif-text)",
                    fontSize: 16.5,
                    borderRadius: 2,
                    padding: "11px 13px",
                  }}
                >
                  <span style={{ flex: "1 1 auto", minWidth: 0 }}>{text}</span>
                  <span className="lease-question-suggestion-action" style={{ flex: "none", fontFamily: "var(--font-mono-editorial)", fontSize: 10 }}>
                    Ask
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {thread.map((entry) => (
          <ThreadItem key={entry.id} entry={entry} activeCitationId={activeCitationId} onViewCitation={onViewCitation} onRetry={onAsk} />
        ))}
      </div>

      <div style={{ flex: "none", borderTop: "1px solid var(--l-line)", background: "var(--l-surface)", padding: "14px 22px 16px" }}>
        <form onSubmit={handleSubmit} style={{ display: "flex", gap: 8, alignItems: "stretch" }}>
          <input
            type="text"
            value={draft}
            onChange={(event) => onDraftChange(event.target.value)}
            placeholder="Ask about rent, notice, repairs, pets"
            style={{
              flex: "1 1 auto",
              minWidth: 0,
              height: 42,
              padding: "0 13px",
              border: "1px solid var(--l-line-strong)",
              borderRadius: 2,
              background: "var(--l-surface-alt)",
              fontFamily: "var(--font-sans-editorial)",
              fontSize: 14.5,
              color: "var(--l-ink)",
            }}
          />
          <button
            type="submit"
            disabled={!draft.trim()}
            style={{
              cursor: draft.trim() ? "pointer" : "not-allowed",
              flex: "none",
              fontFamily: "var(--font-sans-editorial)",
              height: 42,
              padding: "0 18px",
              background: "var(--l-ink)",
              color: "var(--l-surface)",
              border: "1px solid var(--l-ink)",
              borderRadius: 2,
              fontSize: 14,
              fontWeight: 500,
              opacity: draft.trim() ? 1 : 0.55,
            }}
          >
            Ask
          </button>
        </form>
        <div style={{ marginTop: 9, fontFamily: "var(--font-mono-editorial)", fontSize: 10, color: "var(--l-muted)" }}>
          Answers come from this lease only. Not legal advice.
        </div>
      </div>
    </section>
  );
}

function ThreadItem({
  entry,
  activeCitationId,
  onViewCitation,
  onRetry,
}: {
  entry: ThreadEntry;
  activeCitationId: string | null;
  onViewCitation: (citation: AnswerCitation, question: string) => void;
  onRetry: (question: string) => void;
}) {
  const isUnsupported = entry.status === "answered" && entry.citations.length === 0;
  const hasSources = entry.status === "answered" && entry.citations.length > 0;
  const railColor = isUnsupported ? "var(--l-line-strong)" : ACCENT;

  return (
    <div style={{ animation: "kylFade 220ms ease both" }}>
      <div style={{ fontFamily: "var(--font-mono-editorial)", fontSize: 10, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--l-faint)" }}>
        You asked
      </div>
      <div style={{ marginTop: 5, fontFamily: "var(--font-serif-text)", fontSize: 18, lineHeight: 1.35, color: "var(--l-ink)" }}>
        {entry.question}
      </div>

      {entry.status === "loading" && (
        <div style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 10, fontFamily: "var(--font-mono-editorial)", fontSize: 11, color: "var(--l-muted)" }}>
          <span style={{ display: "flex", gap: 4 }}>
            <span style={{ width: 4, height: 4, borderRadius: "50%", background: ACCENT, animation: "kylPulse 1.2s ease-in-out infinite" }} />
            <span style={{ width: 4, height: 4, borderRadius: "50%", background: ACCENT, animation: "kylPulse 1.2s ease-in-out 0.2s infinite" }} />
            <span style={{ width: 4, height: 4, borderRadius: "50%", background: ACCENT, animation: "kylPulse 1.2s ease-in-out 0.4s infinite" }} />
          </span>
          Reading the lease for this answer
        </div>
      )}

      {entry.status === "answered" && (
        <div style={{ marginTop: 12, paddingLeft: 14, borderLeft: `2px solid ${railColor}` }}>
          <AnswerMarkdown>{entry.answer}</AnswerMarkdown>
          {entry.cached && (
            <div style={{ marginTop: 8, fontFamily: "var(--font-mono-editorial)", fontSize: 10, color: "var(--l-faint)" }}>
              Saved from the same question earlier
            </div>
          )}
          {hasSources && (
            <div style={{ marginTop: 12 }}>
              <div
                style={{
                  fontFamily: "var(--font-mono-editorial)",
                  fontSize: 10,
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  color: "var(--l-faint)",
                  marginBottom: 6,
                }}
              >
                {entry.citations.length > 1 ? "Sources in your lease" : "Source in your lease"}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {entry.citations.map((citation) => {
                  const isActive = activeCitationId === citation.chunk_id;
                  return (
                    <button
                      key={citation.chunk_id}
                      type="button"
                      onClick={() => onViewCitation(citation, entry.question)}
                      aria-pressed={isActive}
                      aria-label={`${isActive ? "Showing" : "Open"} source on page ${citation.page_number}`}
                      style={{
                        cursor: "pointer",
                        textAlign: "left",
                        display: "flex",
                        flexDirection: "column",
                        gap: 3,
                        padding: "8px 11px",
                        borderRadius: 2,
                        transition: "all 180ms ease",
                        fontFamily: "var(--font-mono-editorial)",
                        fontSize: 11.5,
                        border: `1px solid ${isActive ? ACCENT : "var(--l-line-strong)"}`,
                        background: isActive ? "rgba(154,91,60,0.08)" : "var(--l-surface-alt)",
                        color: isActive ? ACCENT : "#3A342C",
                      }}
                    >
                      <span style={{ display: "flex", alignItems: "baseline", gap: 10, width: "100%" }}>
                        <span style={{ flex: "1 1 auto", minWidth: 0, textDecoration: "underline", textUnderlineOffset: 3 }}>
                          Page {citation.page_number}
                        </span>
                        <span style={{ flex: "none", whiteSpace: "nowrap", fontSize: 10, color: isActive ? ACCENT : "var(--l-faint)" }}>
                          {isActive ? "Showing" : "Open"}
                        </span>
                      </span>
                      <span style={{ fontFamily: "var(--font-sans-editorial)", fontSize: 12, lineHeight: 1.35, color: "var(--l-text)" }}>
                        {formatCitationExcerpt(citation.snippet)}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
          {isUnsupported && (
            <div style={{ marginTop: 10, fontSize: 13.5, lineHeight: 1.55, color: "var(--l-text)" }}>
              Nothing in this lease covers that. Try asking about rent, notice periods, repairs, or guests.
            </div>
          )}
        </div>
      )}

      {entry.status === "error" && (
        <div
          style={{
            marginTop: 12,
            padding: "12px 14px",
            border: "1px solid rgba(154,91,60,0.4)",
            background: "rgba(154,91,60,0.07)",
            borderRadius: 2,
            boxShadow: `inset 3px 0 0 ${ACCENT}`,
          }}
        >
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.55, color: "#3A342C" }}>
            {entry.errorMessage ?? "We could not get an answer just now. Your question was not lost."}
          </p>
          <button
            type="button"
            onClick={() => onRetry(entry.question)}
            style={{
              cursor: "pointer",
              fontFamily: "var(--font-sans-editorial)",
              marginTop: 10,
              background: "transparent",
              border: 0,
              padding: 0,
              fontSize: 13.5,
              color: ACCENT,
              borderBottom: `1px solid ${ACCENT}`,
            }}
          >
            Ask again
          </button>
        </div>
      )}
    </div>
  );
}
