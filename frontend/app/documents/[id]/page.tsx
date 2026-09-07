"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { AuthGate } from "@/components/auth-gate";
import { ReadyLeaseWorkspace } from "@/components/ready-lease-workspace";
import { ApiError, getDocument } from "@/lib/api";
import { saveActiveDocumentId, shouldPollDocumentStatus } from "@/lib/active-document";
import { landingFontVariables } from "@/lib/fonts";
import type { UploadedDocument } from "@/types/document";

/** Interim destination for the document library's "Open" action. Reuses the existing,
 * unmodified workspace components (PDF viewer, Q&A, citations) rather than the approved
 * workspace redesign, which is a later roadmap step. */
export default function DocumentWorkspacePage() {
  const params = useParams<{ id: string }>();
  const documentId = params.id;
  const router = useRouter();

  const [document, setDocument] = useState<UploadedDocument | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const timeoutRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    let isCurrent = true;

    async function load() {
      try {
        const doc = await getDocument(documentId);
        if (!isCurrent) return;
        setDocument(doc);
        setError(null);
        if (typeof window !== "undefined") saveActiveDocumentId(window.localStorage, doc.id);
        if (shouldPollDocumentStatus(doc.status)) {
          timeoutRef.current = setTimeout(load, 1500);
        }
      } catch (loadError) {
        if (!isCurrent) return;
        setError(
          loadError instanceof ApiError
            ? loadError.message
            : "This document could not be opened.",
        );
      } finally {
        if (isCurrent) setIsLoading(false);
      }
    }

    void load();
    return () => {
      isCurrent = false;
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [documentId]);

  return (
    <main className={`landing ${landingFontVariables}`} style={{ minHeight: "100vh" }}>
      <AuthGate>
        <div style={{ maxWidth: 1120, margin: "0 auto", padding: "24px 24px 0" }}>
          <Link href="/documents" style={{ fontSize: 13.5, color: "var(--l-muted)" }}>
            &larr; Back to your documents
          </Link>
        </div>

        {isLoading && (
          <p
            style={{
              maxWidth: 1120,
              margin: "0 auto",
              padding: "32px 24px",
              fontFamily: "var(--font-mono-editorial)",
              fontSize: 12.5,
              color: "var(--l-muted)",
            }}
          >
            Opening your document&hellip;
          </p>
        )}

        {!isLoading && error && (
          <div style={{ maxWidth: 1120, margin: "0 auto", padding: "32px 24px" }}>
            <p role="alert" style={{ fontSize: 15, color: "var(--l-accent)" }}>
              {error}
            </p>
            <Link href="/documents" style={{ fontSize: 14, color: "var(--l-ink)", textDecoration: "underline" }}>
              Return to your documents
            </Link>
          </div>
        )}

        {!isLoading && !error && document && document.status === "ready" && (
          <ReadyLeaseWorkspace document={document} onUploadAnother={() => router.push("/documents")} />
        )}

        {!isLoading && !error && document && document.status === "failed" && (
          <div style={{ maxWidth: 1120, margin: "0 auto", padding: "32px 24px" }}>
            <p role="alert" style={{ fontSize: 15, color: "var(--l-accent)" }}>
              {document.error_message ?? "This document could not be processed. Please upload it again."}
            </p>
            <Link href="/documents" style={{ fontSize: 14, color: "var(--l-ink)", textDecoration: "underline" }}>
              Return to your documents
            </Link>
          </div>
        )}

        {!isLoading && !error && document && shouldPollDocumentStatus(document.status) && (
          <p
            style={{
              maxWidth: 1120,
              margin: "0 auto",
              padding: "32px 24px",
              fontFamily: "var(--font-mono-editorial)",
              fontSize: 12.5,
              color: "var(--l-muted)",
            }}
          >
            Still preparing this document&hellip;
          </p>
        )}
      </AuthGate>
    </main>
  );
}
