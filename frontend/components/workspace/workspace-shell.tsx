"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";

import { SignOutButton } from "@/components/auth-gate";
import { useNarrowViewport } from "@/components/landing/hooks";
import { landingFontVariables } from "@/lib/fonts";
import type { AnswerCitation, UploadedDocument } from "@/types/document";

import { findHighlightQuestion } from "./thread-utils";
import { useQuestionThread } from "./use-question-thread";
import { WorkspaceAskPanel } from "./workspace-ask-panel";
import { WorkspacePdfPane } from "./workspace-pdf-pane";

const MOBILE_BREAKPOINT = 860;

interface WorkspaceShellProps {
  document: UploadedDocument;
}

export function WorkspaceShell({ document }: WorkspaceShellProps) {
  const isMobile = useNarrowViewport(MOBILE_BREAKPOINT);
  const [mobileTab, setMobileTab] = useState<"doc" | "ask">("doc");
  const [currentPage, setCurrentPage] = useState(1);
  const [numPages, setNumPages] = useState(0);
  const [activeCitation, setActiveCitation] = useState<AnswerCitation | null>(null);
  const [highlightRequestId, setHighlightRequestId] = useState(0);

  const { thread, draft, setDraft, ask } = useQuestionThread(document.id);

  function viewCitation(citation: AnswerCitation) {
    setActiveCitation(citation);
    setHighlightRequestId((requestId) => requestId + 1);
    setCurrentPage(citation.page_number);
    setMobileTab("doc");
  }

  function clearHighlight() {
    setActiveCitation(null);
  }

  const highlightQuestion = findHighlightQuestion(thread, activeCitation?.chunk_id ?? null);

  const showDocTab = !isMobile || mobileTab === "doc";
  const showAskTab = !isMobile || mobileTab === "ask";

  return (
    <div className={`landing ${landingFontVariables}`} style={{ height: "100vh", overflow: "hidden", display: "flex", flexDirection: "column" }}>
      <header style={{ flex: "none", background: "rgba(246,243,237,0.96)", borderBottom: "1px solid var(--l-line)" }}>
        <div style={{ maxWidth: 1440, margin: "0 auto", padding: "0 22px", height: 58, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 18 }}>
          <div style={{ flex: "1 1 auto", display: "flex", alignItems: "center", gap: 14, minWidth: 0 }}>
            <Link href="/" style={{ display: "flex", alignItems: "center", gap: 9, flex: "none" }} aria-label="Know Your Lease home">
              <span
                aria-hidden="true"
                style={{ width: 14, height: 18, border: "1.5px solid var(--l-ink)", borderRadius: 1, display: "block", background: "var(--l-surface-alt)" }}
              />
              <span style={{ fontFamily: "var(--font-serif-display)", fontSize: 19, letterSpacing: "-0.005em" }}>Know Your Lease</span>
            </Link>
            <span style={{ width: 1, height: 20, background: "var(--l-line-strong)", flex: "none" }} />
            <Link href="/documents" style={{ fontSize: 13.5, color: "var(--l-text)", whiteSpace: "nowrap", flex: "none" }}>
              Back to documents
            </Link>
            <span style={{ width: 1, height: 20, background: "var(--l-line-strong)", flex: "none" }} />
            <span
              style={{
                flex: "1 1 auto",
                minWidth: 0,
                fontFamily: "var(--font-serif-text)",
                fontSize: 16,
                color: "var(--l-ink-soft)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {document.filename}
            </span>
          </div>
          <div style={{ flex: "none", display: "flex", alignItems: "center", gap: 12 }}>
            {numPages > 0 && (
              <span style={{ fontFamily: "var(--font-mono-editorial)", fontSize: 10.5, color: "var(--l-muted)", whiteSpace: "nowrap" }}>
                {numPages} pages
              </span>
            )}
            <SignOutButton />
          </div>
        </div>
      </header>

      {isMobile && (
        <div style={{ flex: "none", borderBottom: "1px solid var(--l-line)", background: "var(--l-surface)" }}>
          <div style={{ margin: "0 auto", padding: "8px 16px", display: "flex", gap: 6 }}>
            <MobileTabButton active={mobileTab === "doc"} onClick={() => setMobileTab("doc")}>
              Document
            </MobileTabButton>
            <MobileTabButton active={mobileTab === "ask"} onClick={() => setMobileTab("ask")}>
              Ask
            </MobileTabButton>
          </div>
        </div>
      )}

      <main style={{ flex: "1 1 auto", minHeight: 0, width: "100%", maxWidth: 1440, margin: "0 auto", display: "flex", alignItems: "stretch" }}>
        <WorkspacePdfPane
          documentId={document.id}
          currentPage={currentPage}
          onPageChange={setCurrentPage}
          onNumPagesChange={setNumPages}
          highlightText={activeCitation?.snippet ?? null}
          highlightPageNumber={activeCitation?.page_number ?? null}
          highlightQuestion={highlightQuestion}
          highlightRequestId={highlightRequestId}
          onClearHighlight={clearHighlight}
          hidden={!showDocTab}
        />
        <WorkspaceAskPanel
          thread={thread}
          draft={draft}
          onDraftChange={setDraft}
          onAsk={ask}
          activeCitationId={activeCitation?.chunk_id ?? null}
          onViewCitation={(citation) => viewCitation(citation)}
          hidden={!showAskTab}
        />
      </main>
    </div>
  );
}

function MobileTabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        cursor: "pointer",
        fontFamily: "var(--font-sans-editorial)",
        flex: 1,
        height: 36,
        borderRadius: 2,
        fontSize: 13.5,
        transition: "all 180ms ease",
        border: `1px solid ${active ? "var(--l-ink)" : "var(--l-line-strong)"}`,
        background: active ? "var(--l-ink)" : "transparent",
        color: active ? "var(--l-surface)" : "var(--l-text)",
      }}
    >
      {children}
    </button>
  );
}
