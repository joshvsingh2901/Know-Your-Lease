import type { QuestionAnswer, UploadedDocument } from "@/types/document";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export function getDocumentPdfUrl(documentId: string): string {
  return `${API_BASE_URL}/documents/${encodeURIComponent(documentId)}/pdf`;
}

export class ApiError extends Error {
  constructor(message: string, public readonly status?: number, public readonly code?: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function getErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const error = (await response.json()) as {
      detail?: string | Array<{ msg?: string }> | { message?: string };
    };
    if (typeof error.detail === "string") return error.detail;
    if (error.detail && typeof error.detail === "object" && "message" in error.detail) {
      return typeof error.detail.message === "string" ? error.detail.message : fallback;
    }
    if (Array.isArray(error.detail)) {
      const details = error.detail.flatMap((item) => (item.msg ? [item.msg] : []));
      if (details.length) return details.join(" ");
    }
  } catch {
    // The API did not return JSON, so keep the safe user-facing fallback.
  }
  return fallback;
}

export async function listDocuments(): Promise<UploadedDocument[]> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/documents`, { cache: "no-store" });
  } catch {
    throw new ApiError("Saved documents could not be loaded. Check that the backend is running.");
  }
  if (!response.ok) {
    throw new ApiError(await getErrorMessage(response, "Saved documents could not be loaded."), response.status);
  }
  const body = (await response.json()) as { items: UploadedDocument[] };
  return body.items;
}

export async function uploadDocument(file: File): Promise<UploadedDocument> {
  const body = new FormData();
  body.append("file", file);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/documents`, {
      method: "POST",
      body,
    });
  } catch {
    throw new ApiError(
      `Could not reach the document service at ${API_BASE_URL}. Check that the backend is running and this frontend address is allowed.`,
    );
  }

  if (!response.ok) {
    const message = await getErrorMessage(
      response,
      "Your lease could not be uploaded. Please try again.",
    );
    throw new ApiError(message, response.status);
  }

  return (await response.json()) as UploadedDocument;
}

export async function getDocument(
  documentId: string,
  signal?: AbortSignal,
): Promise<UploadedDocument> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/documents/${encodeURIComponent(documentId)}`, {
      method: "GET",
      signal,
      cache: "no-store",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(
      `Could not check document status at ${API_BASE_URL}. The backend may be unavailable.`,
    );
  }

  if (!response.ok) {
    const message = await getErrorMessage(response, "Document status could not be loaded.");
    throw new ApiError(message, response.status);
  }
  return (await response.json()) as UploadedDocument;
}

export async function askDocumentQuestion(
  documentId: string,
  question: string,
): Promise<QuestionAnswer> {
  let response: Response;
  try {
    response = await fetch(
      `${API_BASE_URL}/documents/${encodeURIComponent(documentId)}/questions`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      },
    );
  } catch {
    throw new ApiError(
      `Could not reach the question service at ${API_BASE_URL}. Check that the backend is running.`,
    );
  }

  if (!response.ok) {
    const message = await getErrorMessage(
      response,
      "Your question could not be answered. Please try again.",
    );
    throw new ApiError(message, response.status);
  }

  return (await response.json()) as QuestionAnswer;
}
