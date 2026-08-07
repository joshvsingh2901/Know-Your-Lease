export type DocumentStatus = "uploaded";

export interface UploadedDocument {
  id: string;
  filename: string;
  status: DocumentStatus;
  created_at: string;
}
