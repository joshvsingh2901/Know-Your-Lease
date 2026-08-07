"use client";

import dynamic from "next/dynamic";

interface PdfViewerProps {
  documentId: string;
  pageNumber: number;
  highlightText: string | null;
  onPageChange: (pageNumber: number) => void;
}

export const PdfViewer = dynamic<PdfViewerProps>(
  () => import("./pdf-viewer-client").then((module) => module.PdfViewerClient),
  {
    ssr: false,
    loading: () => (
      <section className="grid min-h-[32.5rem] place-items-center rounded-2xl border border-[var(--line)] bg-white p-6 text-sm text-[var(--muted)]">
        Loading lease viewer…
      </section>
    ),
  },
);
