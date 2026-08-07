"use client";

import { ChangeEvent, DragEvent, useRef, useState } from "react";

import { ApiError, uploadDocument } from "@/lib/api";
import type { UploadedDocument } from "@/types/document";

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
      setDocument(uploaded);
    } catch (uploadError) {
      setError(uploadError instanceof ApiError ? uploadError.message : "Upload failed. Please try again.");
    } finally {
      setIsUploading(false);
    }
  }

  function reset() {
    setFile(null);
    setDocument(null);
    setError(null);
    if (inputRef.current) inputRef.current.value = "";
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
            Stage 1
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
            <div className="rounded-xl border border-[#b9d8c3] bg-[var(--success-bg)] p-5 sm:p-6">
              <div className="flex items-start gap-4">
                <span className="grid size-10 shrink-0 place-items-center rounded-full bg-[var(--success)] text-white" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none" className="size-5" stroke="currentColor" strokeWidth="2"><path d="m6 12 4 4 8-9" strokeLinecap="round" strokeLinejoin="round" /></svg>
                </span>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-[var(--success)]">Lease uploaded</p>
                  <p className="mt-1 truncate text-sm font-medium text-[var(--navy)]">{document.filename}</p>
                  <dl className="mt-4 grid gap-3 text-xs sm:grid-cols-2">
                    <div><dt className="text-[var(--muted)]">Document ID</dt><dd className="mt-1 break-all font-mono text-[var(--ink)]">{document.id}</dd></div>
                    <div><dt className="text-[var(--muted)]">Status</dt><dd className="mt-1 font-semibold capitalize text-[var(--ink)]">{document.status}</dd></div>
                  </dl>
                </div>
              </div>
              <div className="mt-5 border-t border-[#cfe3d5] pt-4">
                <p className="text-sm leading-6 text-[var(--muted)]">Your lease is uploaded. Document indexing and questions will be enabled in the next build stage.</p>
                <button type="button" onClick={reset} className="mt-3 text-sm font-semibold text-[var(--success)] underline decoration-[#9ac4a7] underline-offset-4">Upload another lease</button>
              </div>
            </div>
          )}

          <div aria-live="polite">
            {error && <p role="alert" className="mt-4 rounded-lg border border-[#ebc4bf] bg-[var(--error-bg)] px-4 py-3 text-sm text-[var(--error)]">{error}</p>}
          </div>
        </div>
      </div>

      <div className="mt-5 rounded-xl border border-[var(--line)] bg-[#efede6] px-5 py-4 text-sm text-[var(--muted)]">
        <p><span className="font-semibold text-[var(--navy)]">Questions are coming next.</span> This build securely transports the PDF metadata; it does not yet read or analyze lease contents.</p>
      </div>
    </section>
  );
}
