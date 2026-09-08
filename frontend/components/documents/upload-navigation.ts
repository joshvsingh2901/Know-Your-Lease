import type { DocumentStatus } from "@/types/document";

/** Decides whether a document status update should send the user into its dedicated
 * workspace. Only ever true for the document this browser session itself just
 * uploaded, and only on the transition into "ready" -- an unrelated document reaching
 * ready in the background (e.g. another tab, another upload finishing later) must
 * never yank the user away from what they are doing. */
export function shouldEnterWorkspace(
  uploadedDocumentId: string | null,
  updatedDocumentId: string,
  updatedStatus: DocumentStatus,
): boolean {
  return uploadedDocumentId !== null && uploadedDocumentId === updatedDocumentId && updatedStatus === "ready";
}
