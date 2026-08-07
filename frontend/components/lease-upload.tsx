"use client";

import { ChangeEvent, DragEvent, useEffect, useRef, useState } from "react";

import { ApiError, getDocument, uploadDocument } from "@/lib/api";
import {
  clearActiveDocumentId,
  restoreActiveDocument,
  saveActiveDocumentId,
  shouldPollDocumentStatus,
} from "@/lib/active-document";
import type { UploadedDocument } from "@/types/document";

import { ReadyLeaseWorkspace } from "./ready-lease-workspace";

const MAX_FILE_SIZE = 20 * 1024 * 1024;

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function validateFile(file: File): string | null {
  const acceptedTypes = ["", "application/pdf", "application/x-pdf"];
  if (!file.name.toLowerCase().endsWith(".pdf") || !acceptedTypes.includes(file.type)) {
    return "Choose a PDF file to continue.";
  }
  if (file.size > MAX_FILE_SIZE) return "PDF files must be 20 MB or smaller.";
  return null;
}

export function LeaseUpload() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [document, setDocument] = useState<UploadedDocument | null>(null);
  const [isRestoringDocument, setIsRestoringDocument] = useState(true);
  const documentId = document?.id;
  const documentStatus = document?.status;

  useEffect(() => {
    let isCurrent = true;

    async function restore() {
      try {
        const restoredDocument = await restoreActiveDocument(window.localStorage, getDocument);
        if (isCurrent && restoredDocument) setDocument(restoredDocument);
      } catch (restoreError) {
        if (isCurrent) {
          setError(
            restoreError instanceof ApiError
              ? restoreError.message
              : "Your saved lease could not be restored. Please try again.",
          );
        }
      } finally {
        if (isCurrent) setIsRestoringDocument(false);
      }
    }

    void restore();
    return () => {
      isCurrent = false;
    };
  }, []);

  useEffect(() => {
    if (!documentId || !documentStatus || !shouldPollDocumentStatus(documentStatus)) return;

    const controller = new AbortController();
    let timeout: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;

    async function pollStatus() {
      try {
        const latest = await getDocument(documentId!, controller.signal);
        failures = 0;
        if (latest.status === "failed") {
          clearActiveDocumentId(window.localStorage);
        } else if (shouldPollDocumentStatus(latest.status)) {
          timeout = setTimeout(pollStatus, 1500);
        }
        setDocument(latest);
      } catch (pollError) {
        if (controller.signal.aborted) return;
        failures += 1;
        if (failures < 3) {
          timeout = setTimeout(pollStatus, 2000);
        } else {
          setError(
            pollError instanceof ApiError
              ? pollError.message
              : "Document processing status could not be checked.",
          );
        }
      }
    }

    timeout = setTimeout(pollStatus, 500);
    return () => {
      controller.abort();
      if (timeout) clearTimeout(timeout);
    };
  }, [documentId, documentStatus]);

  function chooseFile(nextFile: File | undefined) {
    if (!nextFile) return;
    const validationError = validateFile(nextFile);
    setError(validationError);
    setFile(validationError ? null : nextFile);
    setDocument(null);
  }

  function handleFileInput(event: ChangeEvent<HTMLInputElement>) {
    chooseFile(event.target.files?.[0]);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    chooseFile(event.dataTransfer.files[0]);
  }

  async function handleUpload() {
    if (!file) return;
    setIsUploading(true);
    setError(null);
    try {
      const uploaded = await uploadDocument(file);
      saveActiveDocumentId(window.localStorage, uploaded.id);
      setDocument(uploaded);
    } catch (uploadError) {
      setError(uploadError instanceof ApiError ? uploadError.message : "Upload failed. Please try again.");
    } finally {
      setIsUploading(false);
    }
  }

  function reset() {
    clearActiveDocumentId(window.localStorage);
    setFile(null);
    setDocument(null);
    setError(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  if (isRestoringDocument) {
    return null;
  }

  if (document?.status === "ready") {
    return <ReadyLeaseWorkspace document={document} onUploadAnother={reset} />;
  }

  return (
    <section className="mx-auto mt-12 max-w-3xl" aria-labelledby="upload-heading">
      <div className="overflow-hidden rounded-2xl border border-[var(--line)] bg-white shadow-[0_18px_60px_rgba(19,43,58,0.08)]">
        <div className="flex items-center justify-between border-b border-[var(--line)] px-5 py-4 sm:px-7">
          <div>
            <h2 id="upload-heading" className="font-semibold text-[var(--navy)]">Add your lease</h2>
            <p className="mt-0.5 text-sm text-[var(--muted)]">PDF only · up to 20 MB</p>
          </div>
          <span className="rounded-full border border-[var(--line)] bg-[var(--paper)] px-3 py-1 font-mono text-[10px] uppercase tracking-wider text-[var(--muted)]">
            Stage 4
          </span>
        </div>

        <div className="p-5 sm:p-7">
          {!document ? (
            <>
              <div
                className={`upload-hatch flex min-h-56 cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-5 py-10 text-center transition-colors ${
                  isDragging
                    ? "border-[var(--accent)] bg-[#fbf6f2]"
                    : "border-[#c8cbc7] hover:border-[var(--accent)]"
                }`}
                role="button"
                tabIndex={0}
                onClick={() => inputRef.current?.click()}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") inputRef.current?.click();
                }}
                onDragEnter={(event) => {
                  event.preventDefault();
                  setIsDragging(true);
                }}
                onDragOver={(event) => event.preventDefault()}
                onDragLeave={() => setIsDragging(false)}
                onDrop={handleDrop}
              >
                <span className="mb-5 grid size-12 place-items-center rounded-full border border-[var(--line)] bg-white text-[var(--navy)] shadow-sm" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none" className="size-5" stroke="currentColor" strokeWidth="1.8">
                    <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </span>
                <p className="font-semibold text-[var(--navy)]">Drop your lease here</p>
                <p className="mt-2 text-sm text-[var(--muted)]">or <span className="font-semibold text-[var(--accent)]">browse your files</span></p>
                <input
                  ref={inputRef}
                  type="file"
                  accept="application/pdf,.pdf"
                  className="sr-only"
                  onChange={handleFileInput}
                  aria-label="Choose a lease PDF"
                />
              </div>

              {file && (
                <div className="mt-4 flex flex-col gap-4 rounded-xl border border-[var(--line)] bg-[var(--paper)] p-4 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-[var(--navy)]">{file.name}</p>
                    <p className="mt-1 text-xs text-[var(--muted)]">{formatBytes(file.size)} · Ready to upload</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <button type="button" onClick={reset} disabled={isUploading} className="rounded-lg px-3 py-2 text-sm font-medium text-[var(--muted)] hover:text-[var(--navy)] disabled:opacity-50">
                      Remove
                    </button>
                    <button type="button" onClick={handleUpload} disabled={isUploading} className="rounded-lg bg-[var(--accent)] px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[var(--accent-dark)] disabled:cursor-wait disabled:opacity-65">
                      {isUploading ? "Uploading…" : "Upload lease"}
                    </button>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className={`rounded-xl border p-5 sm:p-6 ${
              document.status === "failed"
                ? "border-[#ebc4bf] bg-[var(--error-bg)]"
                : "border-[#c9d3d8] bg-[#f1f5f6]"
            }`}>
              <div className="flex items-start gap-4">
                <span className={`grid size-10 shrink-0 place-items-center rounded-full text-white ${
                  document.status === "failed"
                    ? "bg-[var(--error)]"
                    : "bg-[var(--navy)]"
                }`} aria-hidden="true">
                  {document.status === "failed" ? (
                    <span className="text-lg font-semibold">!</span>
                  ) : (
                    <span className="size-5 animate-spin rounded-full border-2 border-white/35 border-t-white" />
                  )}
                </span>
                <div className="min-w-0 flex-1">
                  <p className={`font-semibold ${
                    document.status === "failed"
                      ? "text-[var(--error)]"
                      : "text-[var(--navy)]"
                  }`}>
                    {document.status === "uploaded" && "Lease uploaded"}
                    {document.status === "processing" && "Processing your lease"}
                    {document.status === "failed" && "Processing failed"}
                  </p>
                  <p className="mt-1 truncate text-sm font-medium text-[var(--navy)]">{document.filename}</p>
                  <dl className="mt-4 grid gap-3 text-xs sm:grid-cols-2">
                    <div><dt className="text-[var(--muted)]">Document ID</dt><dd className="mt-1 break-all font-mono text-[var(--ink)]">{document.id}</dd></div>
                    <div><dt className="text-[var(--muted)]">Status</dt><dd className="mt-1 font-semibold capitalize text-[var(--ink)]">{document.status}</dd></div>
                  </dl>
                </div>
              </div>
              <div className="mt-5 border-t border-current/10 pt-4">
                <p className="text-sm leading-6 text-[var(--muted)]">
                  {document.status === "uploaded" && "Upload complete. Document processing will begin shortly."}
                  {document.status === "processing" && "Extracting clauses and creating the document index…"}
                  {document.status === "failed" && (document.error_message ?? "This lease could not be indexed. Please try another PDF.")}
                </p>
                <button type="button" onClick={reset} className={`mt-3 text-sm font-semibold underline underline-offset-4 ${
                  document.status === "failed" ? "text-[var(--error)]" : "text-[var(--success)]"
                }`}>Upload another lease</button>
              </div>
            </div>
          )}

          <div aria-live="polite">
            {error && <p role="alert" className="mt-4 rounded-lg border border-[#ebc4bf] bg-[var(--error-bg)] px-4 py-3 text-sm text-[var(--error)]">{error}</p>}
          </div>
        </div>
      </div>

      <div className="mt-5 rounded-xl border border-[var(--line)] bg-[#efede6] px-5 py-4 text-sm text-[var(--muted)]">
        <p>
          <span className="font-semibold text-[var(--navy)]">Questions unlock when your lease is ready.</span>{" "}
          Answers will be grounded in this document and include source excerpts.
        </p>
      </div>
    </section>
  );
}
