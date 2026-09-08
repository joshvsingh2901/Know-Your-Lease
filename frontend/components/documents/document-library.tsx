"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChangeEvent, useEffect, useRef, useState } from "react";

import { SignOutButton } from "@/components/auth-gate";
import { usePrefersReducedMotion } from "@/components/landing/hooks";
import { ApiError, listDocuments, uploadDocument, getDocument } from "@/lib/api";
import { saveActiveDocumentId, shouldPollDocumentStatus } from "@/lib/active-document";
import type { DocumentStatus, UploadedDocument } from "@/types/document";

import { shouldEnterWorkspace } from "./upload-navigation";

const MAX_FILE_SIZE = 20 * 1024 * 1024;
const ACCENT = "var(--l-accent)";
const POLL_DELAY_MS = 1500;
const MAX_POLL_FAILURES = 3;

function validateFile(file: File): string | null {
  const isPdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name);
  if (!isPdf) return "That file is not a PDF. Know Your Lease reads PDF leases only.";
  if (file.size > MAX_FILE_SIZE) {
    const mb = (file.size / (1024 * 1024)).toFixed(1);
    return `That file is ${mb} MB. The limit is 20 MB.`;
  }
  return null;
}

function formatSize(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatUploadedAt(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Uploaded recently";
  const diffMs = Date.now() - date.getTime();
  if (diffMs >= 0 && diffMs < 60_000) return "Uploaded just now";
  return `Uploaded ${date.toLocaleDateString("en-US", { day: "numeric", month: "long", year: "numeric" })}`;
}

function statusPresentation(status: DocumentStatus, errorMessage: string | null) {
  switch (status) {
    case "uploaded":
      return { label: "Preparing to process", busy: true, failed: false, dot: "#B4AB9C" };
    case "queued":
      return { label: "Queued for processing", busy: true, failed: false, dot: "#B4AB9C" };
    case "processing":
      return { label: "Preparing your document", busy: true, failed: false, dot: "#B4AB9C" };
    case "ready":
      return { label: "Ready to open", busy: false, failed: false, dot: "#6F8C6A" };
    case "failed":
      return {
        label: errorMessage ?? "Processing failed. Upload the file again to continue.",
        busy: false,
        failed: true,
        dot: ACCENT,
      };
  }
}

type LibraryState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "loaded"; documents: UploadedDocument[] };

export function DocumentLibrary() {
  const router = useRouter();
  const reducedMotion = usePrefersReducedMotion();
  const inputRef = useRef<HTMLInputElement>(null);
  const pollingIds = useRef<Set<string>>(new Set());
  const pollFailures = useRef<Map<string, number>>(new Map());
  const timeouts = useRef<ReturnType<typeof setTimeout>[]>([]);
  const loadToken = useRef(0);
  const uploadedDocumentId = useRef<string | null>(null);

  const [library, setLibrary] = useState<LibraryState>({ kind: "loading" });
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);

  function fetchDocuments() {
    const token = ++loadToken.current;
    listDocuments()
      .then((items) => {
        if (loadToken.current !== token) return;
        setLibrary({ kind: "loaded", documents: items });
      })
      .catch((loadError) => {
        if (loadToken.current !== token) return;
        setLibrary({
          kind: "error",
          message:
            loadError instanceof ApiError ? loadError.message : "Your documents could not be loaded. Please try again.",
        });
      });
  }

  function retryLoadDocuments() {
    setLibrary({ kind: "loading" });
    fetchDocuments();
  }

  useEffect(() => {
    fetchDocuments();
  }, []);

  useEffect(() => {
    const activeTimeouts = timeouts.current;
    return () => {
      activeTimeouts.forEach(clearTimeout);
    };
  }, []);

  function schedulePoll(documentId: string, delay: number) {
    const timeout = setTimeout(async () => {
      try {
        const latest = await getDocument(documentId);
        pollFailures.current.delete(documentId);
        setLibrary((current) =>
          current.kind === "loaded"
            ? { kind: "loaded", documents: current.documents.map((doc) => (doc.id === documentId ? latest : doc)) }
            : current,
        );
        const enterWorkspace = shouldEnterWorkspace(uploadedDocumentId.current, latest.id, latest.status);
        if (shouldPollDocumentStatus(latest.status) && !enterWorkspace) {
          schedulePoll(documentId, POLL_DELAY_MS);
        } else {
          pollingIds.current.delete(documentId);
        }
        if (enterWorkspace) {
          uploadedDocumentId.current = null;
          router.push(`/documents/${latest.id}`);
        }
      } catch {
        const failures = (pollFailures.current.get(documentId) ?? 0) + 1;
        pollFailures.current.set(documentId, failures);
        if (failures < MAX_POLL_FAILURES) {
          schedulePoll(documentId, POLL_DELAY_MS);
        } else {
          pollingIds.current.delete(documentId);
        }
      }
    }, delay);
    timeouts.current.push(timeout);
  }

  useEffect(() => {
    if (library.kind !== "loaded") return;
    for (const doc of library.documents) {
      if (shouldPollDocumentStatus(doc.status) && !pollingIds.current.has(doc.id)) {
        pollingIds.current.add(doc.id);
        schedulePoll(doc.id, POLL_DELAY_MS);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [library]);

  function openPicker() {
    if (inputRef.current) inputRef.current.value = "";
    inputRef.current?.click();
  }

  async function handleFilePicked(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    const validationError = validateFile(file);
    if (validationError) {
      setUploadError(validationError);
      return;
    }

    setUploadError(null);
    setIsUploading(true);
    setPendingFile(file);
    try {
      const uploaded = await uploadDocument(file);
      if (typeof window !== "undefined") saveActiveDocumentId(window.localStorage, uploaded.id);
      uploadedDocumentId.current = uploaded.id;
      setLibrary((current) =>
        current.kind === "loaded"
          ? { kind: "loaded", documents: [uploaded, ...current.documents] }
          : { kind: "loaded", documents: [uploaded] },
      );
      if (shouldEnterWorkspace(uploadedDocumentId.current, uploaded.id, uploaded.status)) {
        uploadedDocumentId.current = null;
        router.push(`/documents/${uploaded.id}`);
      }
    } catch (uploadCaughtError) {
      setUploadError(
        uploadCaughtError instanceof ApiError ? uploadCaughtError.message : "Your lease could not be uploaded. Please try again.",
      );
    } finally {
      setIsUploading(false);
      setPendingFile(null);
    }
  }

  const documents = library.kind === "loaded" ? library.documents : null;
  const sortedDocuments = documents
    ? [...documents].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    : null;
  const hasDocs = Boolean(sortedDocuments && sortedDocuments.length > 0);
  const isEmpty = library.kind === "loaded" && library.documents.length === 0 && !isUploading;

  return (
    <div style={{ minHeight: "100vh" }}>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        onChange={handleFilePicked}
        aria-label="Choose a lease PDF"
        style={{ position: "absolute", width: 1, height: 1, opacity: 0, pointerEvents: "none" }}
      />

      <header
        style={{
          position: "sticky",
          top: 0,
          zIndex: 20,
          background: "rgba(246,243,237,0.94)",
          backdropFilter: "blur(8px)",
          borderBottom: "1px solid var(--l-line)",
        }}
      >
        <div
          style={{
            maxWidth: 1000,
            margin: "0 auto",
            padding: "0 24px",
            height: 60,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 20,
          }}
        >
          <Link href="/" style={{ display: "flex", alignItems: "center", gap: 10 }} aria-label="Know Your Lease home">
            <span
              aria-hidden="true"
              style={{
                width: 15,
                height: 19,
                border: "1.5px solid var(--l-ink)",
                borderRadius: 1,
                display: "block",
                background: "var(--l-surface-alt)",
              }}
            />
            <span style={{ fontFamily: "var(--font-serif-display)", fontSize: 20, letterSpacing: "-0.005em" }}>
              Know Your Lease
            </span>
          </Link>
          <div style={{ display: "flex", alignItems: "center", gap: 22 }}>
            <span
              style={{
                fontSize: 14,
                color: "var(--l-ink)",
                borderBottom: `1px solid ${ACCENT}`,
                paddingBottom: 2,
              }}
            >
              Documents
            </span>
            <SignOutButton />
          </div>
        </div>
      </header>

      <main style={{ maxWidth: 1000, margin: "0 auto", padding: "34px 24px 72px" }}>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 20,
            alignItems: "flex-end",
            justifyContent: "space-between",
            paddingBottom: 18,
            borderBottom: "1px solid var(--l-line)",
          }}
        >
          <div style={{ flex: "1 1 340px", minWidth: 0 }}>
            <h1
              style={{
                fontFamily: "var(--font-serif-display)",
                fontWeight: 400,
                fontSize: "clamp(32px, 4.2vw, 42px)",
                lineHeight: 1.05,
                letterSpacing: "-0.01em",
                margin: 0,
              }}
            >
              Your documents
            </h1>
            <p style={{ margin: "10px 0 0", fontSize: 15.5, lineHeight: 1.5, color: "var(--l-text)", maxWidth: "52ch" }}>
              Every lease you upload stays here. Open one to ask questions and read the clause behind each answer.
            </p>
          </div>
          <div style={{ flex: "0 0 auto", display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 7 }}>
            <button
              type="button"
              onClick={openPicker}
              disabled={isUploading}
              style={{
                cursor: isUploading ? "wait" : "pointer",
                display: "inline-flex",
                alignItems: "center",
                height: 44,
                padding: "0 22px",
                background: "var(--l-ink)",
                color: "var(--l-surface)",
                border: "1px solid var(--l-ink)",
                borderRadius: 2,
                fontFamily: "var(--font-sans-editorial)",
                fontSize: 15,
                fontWeight: 500,
                whiteSpace: "nowrap",
                opacity: isUploading ? 0.65 : 1,
              }}
            >
              {isUploading ? "Uploading…" : "Upload a lease"}
            </button>
            <span style={{ fontFamily: "var(--font-mono-editorial)", fontSize: 11, color: "var(--l-muted)", whiteSpace: "nowrap" }}>
              PDF only, up to 20 MB
            </span>
          </div>
        </div>

        {uploadError && (
          <div
            role="alert"
            style={{
              marginTop: 16,
              display: "flex",
              flexWrap: "wrap",
              gap: 10,
              alignItems: "baseline",
              padding: "12px 14px",
              border: "1px solid rgba(154,91,60,0.4)",
              background: "rgba(154,91,60,0.07)",
              borderRadius: 2,
              boxShadow: `inset 3px 0 0 ${ACCENT}`,
              animation: reducedMotion ? "none" : "kylFade 200ms ease both",
            }}
          >
            <span style={{ flex: "1 1 240px", minWidth: 0, fontSize: 14, lineHeight: 1.45, color: "#3A342C" }}>
              {uploadError}
            </span>
            <button
              type="button"
              onClick={openPicker}
              style={{
                cursor: "pointer",
                fontFamily: "var(--font-sans-editorial)",
                background: "transparent",
                border: 0,
                padding: 0,
                fontSize: 13.5,
                color: ACCENT,
                borderBottom: `1px solid ${ACCENT}`,
                whiteSpace: "nowrap",
              }}
            >
              Choose another file
            </button>
          </div>
        )}

        {library.kind === "loading" && (
          <p style={{ marginTop: 32, fontFamily: "var(--font-mono-editorial)", fontSize: 12.5, color: "var(--l-muted)" }}>
            Loading your documents&hellip;
          </p>
        )}

        {library.kind === "error" && <ListLoadError message={library.message} onRetry={retryLoadDocuments} />}

        {library.kind === "loaded" && (hasDocs || isUploading) && (
          <div>
            <div
              style={{
                margin: "24px 0 2px",
                display: "flex",
                alignItems: "baseline",
                justifyContent: "space-between",
                gap: 16,
              }}
            >
              <span style={{ fontFamily: "var(--font-mono-editorial)", fontSize: 11, color: "var(--l-muted)", whiteSpace: "nowrap" }}>
                {(sortedDocuments?.length ?? 0) === 1 ? "1 document" : `${sortedDocuments?.length ?? 0} documents`}
              </span>
              <span style={{ fontFamily: "var(--font-mono-editorial)", fontSize: 11, color: "var(--l-muted)", whiteSpace: "nowrap" }}>
                Most recent first
              </span>
            </div>

            {isUploading && pendingFile && (
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 14,
                  alignItems: "center",
                  padding: "15px 12px 15px 14px",
                  margin: "0 -12px 0 -14px",
                  borderTop: "1px solid var(--l-line)",
                  background: "#FBF8F3",
                }}
              >
                <DocumentIcon borderColor="#CFC7B9" />
                <div style={{ flex: "1 1 230px", minWidth: 0 }}>
                  <div
                    style={{
                      fontFamily: "var(--font-serif-text)",
                      fontSize: 17.5,
                      lineHeight: 1.3,
                      color: "var(--l-ink)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {pendingFile.name}
                  </div>
                  <div style={{ marginTop: 4, fontFamily: "var(--font-mono-editorial)", fontSize: 11, color: "var(--l-muted)" }}>
                    Uploading now &middot; {formatSize(pendingFile.size)}
                  </div>
                </div>
                <div style={{ flex: "1 1 220px", minWidth: 0, display: "flex", alignItems: "center", gap: 9 }}>
                  <span style={{ width: 6, height: 6, borderRadius: "50%", flex: "none", background: "#B4AB9C" }} />
                  <span style={{ fontSize: 13.5, lineHeight: 1.4, color: "#5F594F" }}>Uploading your lease&hellip;</span>
                </div>
                <div style={{ flex: "0 0 auto", display: "flex", alignItems: "center", gap: 10, minWidth: 132, justifyContent: "flex-end" }}>
                  <BusyBar reducedMotion={reducedMotion} />
                </div>
              </div>
            )}

            {sortedDocuments?.map((doc) => (
              <DocumentRow key={doc.id} document={doc} onUploadAgain={openPicker} reducedMotion={reducedMotion} />
            ))}
            <div style={{ borderTop: "1px solid var(--l-line)" }} />
          </div>
        )}

        {isEmpty && (
          <div style={{ marginTop: 32, display: "flex", flexWrap: "wrap", gap: 44, alignItems: "center" }}>
            <div style={{ flex: "1 1 320px", minWidth: 0 }}>
              <h2
                style={{
                  fontFamily: "var(--font-serif-display)",
                  fontWeight: 400,
                  fontSize: 29,
                  lineHeight: 1.12,
                  margin: 0,
                }}
              >
                Nothing here yet. <em style={{ fontStyle: "italic", color: "#3A342C" }}>Start with your lease.</em>
              </h2>
              <p style={{ margin: "12px 0 0", fontSize: 15, lineHeight: 1.55, color: "var(--l-text)", maxWidth: "44ch" }}>
                Upload the PDF your landlord sent you. It takes a minute or two to prepare, then you can ask anything
                about it and see the exact clause behind the answer.
              </p>
            </div>
            <div style={{ flex: "1 1 240px", minWidth: 0, display: "flex", justifyContent: "flex-start" }}>
              <div
                style={{
                  width: "100%",
                  maxWidth: 268,
                  background: "var(--l-surface-alt)",
                  border: "1px solid var(--l-line-strong)",
                  borderRadius: 2,
                  padding: 20,
                  boxShadow: "0 1px 0 rgba(27,26,23,0.04), 0 26px 46px -42px rgba(27,26,23,0.6)",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "baseline",
                    justifyContent: "space-between",
                    borderBottom: "1px solid #EDE7DC",
                    paddingBottom: 9,
                    marginBottom: 14,
                  }}
                >
                  <span style={{ fontFamily: "var(--font-serif-text)", fontSize: 12.5, color: "var(--l-faint)" }}>
                    Your lease, once uploaded
                  </span>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                  <Bar width="100%" />
                  <Bar width="92%" />
                  <Bar width="64%" />
                </div>
                <div
                  style={{
                    margin: "14px -6px",
                    padding: "8px 6px",
                    background: "rgba(154,91,60,0.12)",
                    boxShadow: `inset 3px 0 0 ${ACCENT}`,
                    display: "flex",
                    flexDirection: "column",
                    gap: 7,
                  }}
                >
                  <Bar width="96%" tone="dark" />
                  <Bar width="70%" tone="dark" />
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                  <Bar width="98%" />
                  <Bar width="48%" />
                </div>
              </div>
            </div>
          </div>
        )}

        <p style={{ margin: "24px 0 0", fontFamily: "var(--font-mono-editorial)", fontSize: 11, color: "var(--l-muted)" }}>
          Your documents are private to your account. Not legal advice.
        </p>
      </main>
    </div>
  );
}

function DocumentIcon({ borderColor }: { borderColor: string }) {
  return (
    <span
      style={{
        flex: "none",
        width: 17,
        height: 22,
        border: `1px solid ${borderColor}`,
        borderRadius: 1,
        background: "var(--l-surface-alt)",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        gap: 3,
        padding: "0 3px",
      }}
    >
      <span style={{ height: 1, background: borderColor }} />
      <span style={{ height: 1, background: borderColor }} />
      <span style={{ height: 1, background: borderColor, width: "60%" }} />
    </span>
  );
}

function BusyBar({ reducedMotion }: { reducedMotion: boolean }) {
  return (
    <span style={{ display: "block", width: 96, height: 3, background: "#E6E0D5", borderRadius: 2, overflow: "hidden", position: "relative" }}>
      <span
        style={{
          position: "absolute",
          inset: 0,
          transformOrigin: "left",
          background: ACCENT,
          width: reducedMotion ? "40%" : "30%",
          animation: reducedMotion ? "none" : "kylSlide 1.7s ease-in-out infinite",
        }}
      />
    </span>
  );
}

function Bar({ width, tone = "light" }: { width: string; tone?: "light" | "dark" }) {
  return (
    <span
      style={{
        display: "block",
        height: 5,
        borderRadius: 1,
        width,
        background: tone === "dark" ? "#D8CDBC" : "#E6E0D5",
      }}
    />
  );
}

function ListLoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div
      role="alert"
      style={{
        marginTop: 32,
        display: "flex",
        flexWrap: "wrap",
        gap: 16,
        alignItems: "center",
        justifyContent: "space-between",
        padding: "20px 20px",
        border: "1px solid rgba(154,91,60,0.4)",
        background: "rgba(154,91,60,0.07)",
        borderRadius: 2,
        boxShadow: `inset 3px 0 0 ${ACCENT}`,
      }}
    >
      <span style={{ flex: "1 1 260px", minWidth: 0, fontSize: 15, lineHeight: 1.5, color: "#3A342C" }}>{message}</span>
      <button
        type="button"
        onClick={onRetry}
        style={{
          cursor: "pointer",
          fontFamily: "var(--font-sans-editorial)",
          display: "inline-flex",
          alignItems: "center",
          height: 38,
          padding: "0 18px",
          border: `1px solid ${ACCENT}`,
          background: "rgba(154,91,60,0.08)",
          borderRadius: 2,
          fontSize: 14,
          fontWeight: 500,
          color: ACCENT,
          whiteSpace: "nowrap",
        }}
      >
        Retry
      </button>
    </div>
  );
}

function DocumentRow({
  document,
  onUploadAgain,
  reducedMotion,
}: {
  document: UploadedDocument;
  onUploadAgain: () => void;
  reducedMotion: boolean;
}) {
  const presentation = statusPresentation(document.status, document.error_message);
  const nameColor = presentation.failed ? "#5F594F" : "var(--l-ink)";
  const iconBorder = presentation.failed ? "rgba(154,91,60,0.5)" : document.status === "ready" ? "#BDB4A5" : "#CFC7B9";

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 14,
        alignItems: "center",
        padding: "15px 12px 15px 14px",
        margin: "0 -12px 0 -14px",
        borderTop: "1px solid var(--l-line)",
        background: presentation.busy ? "#FBF8F3" : "transparent",
        boxShadow: presentation.failed ? `inset 3px 0 0 ${ACCENT}` : "inset 0 0 0 rgba(0,0,0,0)",
      }}
    >
      <DocumentIcon borderColor={iconBorder} />
      <div style={{ flex: "1 1 230px", minWidth: 0 }}>
        <div
          style={{
            fontFamily: "var(--font-serif-text)",
            fontSize: 17.5,
            lineHeight: 1.3,
            color: nameColor,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {document.filename}
        </div>
        <div style={{ marginTop: 4, fontFamily: "var(--font-mono-editorial)", fontSize: 11, color: "var(--l-muted)" }}>
          {formatUploadedAt(document.created_at)}
        </div>
      </div>
      <div style={{ flex: "1 1 220px", minWidth: 0, display: "flex", alignItems: "center", gap: 9 }}>
        <span style={{ width: 6, height: 6, borderRadius: "50%", flex: "none", background: presentation.dot }} />
        <span style={{ fontSize: 13.5, lineHeight: 1.4, color: presentation.failed ? ACCENT : "var(--l-text)" }}>
          {presentation.label}
        </span>
      </div>
      <div style={{ flex: "0 0 auto", display: "flex", alignItems: "center", gap: 10, minWidth: 132, justifyContent: "flex-end" }}>
        {presentation.busy && <BusyBar reducedMotion={reducedMotion} />}
        {document.status === "ready" && (
          <Link
            href={`/documents/${document.id}`}
            style={{
              display: "inline-flex",
              alignItems: "center",
              height: 34,
              padding: "0 16px",
              border: "1px solid var(--l-line-strong)",
              background: "var(--l-surface)",
              borderRadius: 2,
              fontSize: 13.5,
              color: "var(--l-ink)",
            }}
          >
            Open
          </Link>
        )}
        {presentation.failed && (
          <button
            type="button"
            onClick={onUploadAgain}
            style={{
              cursor: "pointer",
              fontFamily: "var(--font-sans-editorial)",
              display: "inline-flex",
              alignItems: "center",
              height: 34,
              padding: "0 16px",
              border: `1px solid ${ACCENT}`,
              background: "rgba(154,91,60,0.08)",
              borderRadius: 2,
              fontSize: 13.5,
              color: ACCENT,
              whiteSpace: "nowrap",
            }}
          >
            Upload again
          </button>
        )}
      </div>
    </div>
  );
}
