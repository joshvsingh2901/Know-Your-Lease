import type { DocumentStatus, UploadedDocument } from "@/types/document";

export const ACTIVE_DOCUMENT_STORAGE_KEY = "know-your-lease.active-document-id";

interface StorageLike {
  getItem(key: string): string | null;
  removeItem(key: string): void;
  setItem(key: string, value: string): void;
}

interface StatusError {
  status?: number;
}

export function readActiveDocumentId(storage: StorageLike): string | null {
  const documentId = storage.getItem(ACTIVE_DOCUMENT_STORAGE_KEY)?.trim();
  return documentId || null;
}

export function saveActiveDocumentId(storage: StorageLike, documentId: string): void {
  storage.setItem(ACTIVE_DOCUMENT_STORAGE_KEY, documentId);
}

export function clearActiveDocumentId(storage: StorageLike): void {
  storage.removeItem(ACTIVE_DOCUMENT_STORAGE_KEY);
}

export function shouldPollDocumentStatus(status: DocumentStatus): boolean {
  return status === "uploaded" || status === "queued" || status === "processing";
}

export async function restoreActiveDocument(
  storage: StorageLike,
  loadDocument: (documentId: string) => Promise<UploadedDocument>,
): Promise<UploadedDocument | null> {
  const documentId = readActiveDocumentId(storage);
  if (!documentId) return null;

  try {
    const document = await loadDocument(documentId);
    if (document.status === "failed") {
      clearActiveDocumentId(storage);
      return null;
    }
    return document;
  } catch (error) {
    const status = typeof error === "object" && error !== null
      ? (error as StatusError).status
      : undefined;
    // A 404 means this document doesn't exist or isn't owned by the signed-in user --
    // the stale ID is worthless and should be forgotten. A 401 is about the session,
    // not this document: the ID may still be valid once the user re-authenticates, so
    // it must survive an expired/invalid token rather than being silently discarded.
    if (status !== undefined && status >= 400 && status < 500 && status !== 401) {
      clearActiveDocumentId(storage);
      return null;
    }
    throw error;
  }
}
