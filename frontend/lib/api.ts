import type { UploadedDocument } from "@/types/document";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message);
    this.name = "ApiError";
  }
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
    let message = "Your lease could not be uploaded. Please try again.";
    try {
      const error = (await response.json()) as {
        detail?: string | Array<{ msg?: string }>;
      };
      if (typeof error.detail === "string") {
        message = error.detail;
      } else if (Array.isArray(error.detail)) {
        const details = error.detail.flatMap((item) => (item.msg ? [item.msg] : []));
        if (details.length) message = details.join(" ");
      }
    } catch {
      // The API did not return JSON, so keep the safe user-facing fallback.
    }
    throw new ApiError(message, response.status);
  }

  return (await response.json()) as UploadedDocument;
}
