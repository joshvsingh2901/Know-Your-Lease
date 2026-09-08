"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { AuthGate } from "@/components/auth-gate";
import { WorkspaceShell } from "@/components/workspace/workspace-shell";
import { ApiError, getDocument } from "@/lib/api";
import { saveActiveDocumentId, shouldPollDocumentStatus } from "@/lib/active-document";
import { landingFontVariables } from "@/lib/fonts";
import type { UploadedDocument } from "@/types/document";

export default function DocumentWorkspacePage() {
  const params = useParams<{ id: string }>();
  const documentId = params.id;

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

  const isReady = !isLoading && !error && document?.status === "ready";

  return (
    <AuthGate>
      {isReady && document ? (
        <WorkspaceShell document={document} />
      ) : (
        <main className={`landing ${landingFontVariables}`} style={{ minHeight: "100vh" }}>
          <div style={{ maxWidth: 640, margin: "0 auto", padding: "24px 24px 0" }}>
            <Link href="/documents" style={{ fontSize: 13.5, color: "var(--l-muted)" }}>
              &larr; Back to your documents
            </Link>
          </div>

          {isLoading && (
            <p
              style={{
                maxWidth: 640,
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
            <div style={{ maxWidth: 520, margin: "44px auto 0", padding: "0 24px" }}>
              <h2 style={{ fontFamily: "var(--font-serif-display)", fontWeight: 400, fontSize: 27, lineHeight: 1.14, margin: 0 }}>
                We could not open this document.
              </h2>
              <p style={{ margin: "12px 0 0", fontSize: 14.5, lineHeight: 1.6, color: "var(--l-text)" }}>{error}</p>
              <div style={{ marginTop: 20 }}>
                <Link
                  href="/documents"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    height: 38,
                    padding: "0 18px",
                    border: "1px solid var(--l-line-strong)",
                    background: "var(--l-surface)",
                    borderRadius: 2,
                    fontSize: 13.5,
                    color: "var(--l-ink)",
                  }}
                >
                  Back to documents
                </Link>
              </div>
            </div>
          )}

          {!isLoading && !error && document && document.status === "failed" && (
            <div style={{ maxWidth: 520, margin: "44px auto 0", padding: "0 24px" }}>
              <h2 style={{ fontFamily: "var(--font-serif-display)", fontWeight: 400, fontSize: 27, lineHeight: 1.14, margin: 0 }}>
                This lease could not be processed.
              </h2>
              <p style={{ margin: "12px 0 0", fontSize: 14.5, lineHeight: 1.6, color: "var(--l-text)" }}>
                {document.error_message ?? "Upload the file again from your documents to try once more."}
              </p>
              <div style={{ marginTop: 20 }}>
                <Link
                  href="/documents"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    height: 38,
                    padding: "0 18px",
                    border: "1px solid var(--l-line-strong)",
                    background: "var(--l-surface)",
                    borderRadius: 2,
                    fontSize: 13.5,
                    color: "var(--l-ink)",
                  }}
                >
                  Back to documents
                </Link>
              </div>
            </div>
          )}

          {!isLoading && !error && document && shouldPollDocumentStatus(document.status) && (
            <div style={{ maxWidth: 520, margin: "44px auto 0", padding: "0 24px" }}>
              <h2 style={{ fontFamily: "var(--font-serif-display)", fontWeight: 400, fontSize: 27, lineHeight: 1.14, margin: 0 }}>
                This lease is still being prepared.
              </h2>
              <p style={{ margin: "12px 0 0", fontSize: 14.5, lineHeight: 1.6, color: "var(--l-text)" }}>
                Preparing a document usually takes a minute or two. You can wait here or go back to your documents
                and open it once it is ready.
              </p>
              <div style={{ marginTop: 20, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 14 }}>
                <Link
                  href="/documents"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    height: 38,
                    padding: "0 18px",
                    border: "1px solid var(--l-line-strong)",
                    background: "var(--l-surface)",
                    borderRadius: 2,
                    fontSize: 13.5,
                    color: "var(--l-ink)",
                  }}
                >
                  Back to documents
                </Link>
                <span style={{ fontFamily: "var(--font-mono-editorial)", fontSize: 11, color: "var(--l-muted)", display: "flex", alignItems: "center", gap: 9 }}>
                  <span style={{ display: "block", width: 60, height: 3, background: "#E6E0D5", borderRadius: 2, overflow: "hidden", position: "relative" }}>
                    <span style={{ position: "absolute", inset: 0, width: "30%", background: "var(--l-accent)", animation: "kylSlide 1.7s ease-in-out infinite" }} />
                  </span>
                  Preparing your document
                </span>
              </div>
            </div>
          )}
        </main>
      )}
    </AuthGate>
  );
}
