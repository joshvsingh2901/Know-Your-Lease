export type DocumentStatus = "uploaded" | "processing" | "ready" | "failed";

export interface UploadedDocument {
  id: string;
  filename: string;
  status: DocumentStatus;
  created_at: string;
  updated_at: string;
  error_message: string | null;
}
