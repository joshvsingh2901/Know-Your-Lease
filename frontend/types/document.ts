export type DocumentStatus = "uploaded" | "processing" | "ready" | "failed";

export interface UploadedDocument {
  id: string;
  filename: string;
  status: DocumentStatus;
  created_at: string;
  updated_at: string;
  error_message: string | null;
}

export interface AnswerCitation {
  chunk_id: string;
  page_number: number;
  section_title: string | null;
  snippet: string;
  score: number;
}

export interface QuestionAnswer {
  answer: string;
  citations: AnswerCitation[];
}
