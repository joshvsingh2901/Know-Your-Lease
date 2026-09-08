"use client";

import dynamic from "next/dynamic";

interface WorkspacePdfPaneProps {
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

export const WorkspacePdfPane = dynamic<WorkspacePdfPaneProps>(
  () => import("./workspace-pdf-pane-client").then((module) => module.WorkspacePdfPaneClient),
  {
    ssr: false,
    loading: () => (
      <section
        style={{
          flex: "6 1 480px",
          minWidth: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          borderRight: "1px solid var(--l-line)",
          background: "var(--l-paper-alt)",
          fontFamily: "var(--font-mono-editorial)",
          fontSize: 12.5,
          color: "var(--l-muted)",
        }}
      >
        Loading lease viewer&hellip;
      </section>
    ),
  },
);
