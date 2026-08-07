"use client";

import { useState } from "react";

import type { AnswerCitation, UploadedDocument } from "@/types/document";

import { PdfViewer } from "./pdf-viewer";
import { QuestionPanel } from "./question-panel";

interface ReadyLeaseWorkspaceProps {
  document: UploadedDocument;
  onUploadAnother: () => void;
}

export function ReadyLeaseWorkspace({ document, onUploadAnother }: ReadyLeaseWorkspaceProps) {
  const [activeCitation, setActiveCitation] = useState<AnswerCitation | null>(null);
  const [currentPage, setCurrentPage] = useState(1);

  function viewCitation(citation: AnswerCitation) {
    setActiveCitation(citation);
    setCurrentPage(citation.page_number);
  }

  return (
    <section className="mx-auto mt-12 max-w-6xl">
      <div className="grid gap-5 lg:grid-cols-2 lg:items-start">
        <PdfViewer
          documentId={document.id}
          pageNumber={currentPage}
          highlightText={activeCitation?.snippet ?? null}
          onPageChange={setCurrentPage}
        />

        <div>
          <section className="rounded-2xl border border-[#b9d8c3] bg-[var(--success-bg)] px-5 py-4 shadow-[0_18px_60px_rgba(19,43,58,0.08)]">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.15em] text-[var(--success)]">
                  Lease ready
                </p>
                <p className="mt-1 truncate text-sm font-semibold text-[var(--navy)]">
                  {document.filename}
                </p>
              </div>
              <button
                type="button"
                onClick={onUploadAnother}
                className="shrink-0 text-sm font-semibold text-[var(--success)] underline underline-offset-4"
              >
                Upload another
              </button>
            </div>
          </section>

          <QuestionPanel
            documentId={document.id}
            activeCitationId={activeCitation?.chunk_id ?? null}
            onCitationSelect={viewCitation}
          />
        </div>
      </div>
    </section>
  );
}
