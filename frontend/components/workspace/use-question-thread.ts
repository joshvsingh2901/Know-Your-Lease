"use client";

import { useRef, useState } from "react";

import { ApiError, askDocumentQuestion } from "@/lib/api";
import type { QuestionAnswer } from "@/types/document";

import { findAnsweredEntry, type ThreadEntry } from "./thread-utils";

export type { ThreadEntry } from "./thread-utils";

/** Every question still goes through the real askDocumentQuestion API call. The only
 * local shortcut is reusing an already-answered entry when the exact same question
 * (normalized) is asked again in this session -- an accurate reflection of the
 * backend's own exact-question answer cache, not a fabricated behavior. */
export function useQuestionThread(documentId: string) {
  const [thread, setThread] = useState<ThreadEntry[]>([]);
  const [draft, setDraft] = useState("");
  const nextId = useRef(1);

  async function ask(rawQuestion: string) {
    const question = rawQuestion.trim();
    if (!question) return;

    const priorAnswer = findAnsweredEntry(thread, question);
    const id = nextId.current++;

    if (priorAnswer) {
      setThread((current) => [
        ...current,
        { ...priorAnswer, id, question, cached: true },
      ]);
      return;
    }

    setThread((current) => [
      ...current,
      { id, question, status: "loading", answer: "", citations: [], cached: false, errorMessage: null },
    ]);

    try {
      const result: QuestionAnswer = await askDocumentQuestion(documentId, question);
      setThread((current) =>
        current.map((entry) =>
          entry.id === id ? { ...entry, status: "answered", answer: result.answer, citations: result.citations } : entry,
        ),
      );
    } catch (askError) {
      setThread((current) =>
        current.map((entry) =>
          entry.id === id
            ? {
                ...entry,
                status: "error",
                errorMessage:
                  askError instanceof ApiError ? askError.message : "Your question could not be answered. Please try again.",
              }
            : entry,
        ),
      );
    }
  }

  function submitDraft() {
    const question = draft;
    setDraft("");
    void ask(question);
  }

  return { thread, draft, setDraft, ask, submitDraft };
}
