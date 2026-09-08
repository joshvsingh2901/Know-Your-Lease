import assert from "node:assert/strict";
import test from "node:test";

const { findAnsweredEntry, findHighlightQuestion, formatCitationExcerpt } = await import("../components/workspace/thread-utils.ts");

function citation(chunkId, overrides = {}) {
  return {
    chunk_id: chunkId,
    page_number: 13,
    section_title: "14.2 Pets",
    snippet: "No animal shall be kept in or about the Premises without the prior written consent of the Landlord.",
    score: 0.9,
    ...overrides,
  };
}

function entry(overrides = {}) {
  return {
    id: 1,
    question: "Can I have pets?",
    status: "answered",
    answer: "Yes, with written consent.",
    citations: [],
    cached: false,
    errorMessage: null,
    ...overrides,
  };
}

test("findAnsweredEntry reuses an exact-match answered question, ignoring case and surrounding whitespace", () => {
  const thread = [entry({ id: 1, question: "Can I have pets?" })];
  const match = findAnsweredEntry(thread, "  CAN i have pets?  ");
  assert.equal(match?.id, 1);
});

test("findAnsweredEntry never matches a loading or errored entry for the same question", () => {
  const thread = [
    entry({ id: 1, question: "When is rent due?", status: "loading" }),
    entry({ id: 2, question: "When is rent due?", status: "error" }),
  ];
  assert.equal(findAnsweredEntry(thread, "When is rent due?"), undefined);
});

test("findAnsweredEntry does not match a different question", () => {
  const thread = [entry({ id: 1, question: "Can I have pets?" })];
  assert.equal(findAnsweredEntry(thread, "Can I leave early?"), undefined);
});

test("findHighlightQuestion returns null when no citation is active", () => {
  const thread = [entry({ citations: [citation("chunk-1")] })];
  assert.equal(findHighlightQuestion(thread, null), null);
});

test("findHighlightQuestion finds the question whose answer cited the active source", () => {
  const thread = [
    entry({ id: 1, question: "Can I have pets?", citations: [citation("chunk-1")] }),
    entry({ id: 2, question: "When is rent due?", citations: [citation("chunk-2")] }),
  ];
  assert.equal(findHighlightQuestion(thread, "chunk-2"), "When is rent due?");
});

test("findHighlightQuestion prefers the most recent question when a source is cited by more than one answer", () => {
  const thread = [
    entry({ id: 1, question: "Can I have pets?", citations: [citation("chunk-1")] }),
    entry({ id: 2, question: "What do I need to know before I move out?", citations: [citation("chunk-1")] }),
  ];
  assert.equal(findHighlightQuestion(thread, "chunk-1"), "What do I need to know before I move out?");
});

test("findHighlightQuestion returns null when the active citation id matches nothing in the thread", () => {
  const thread = [entry({ citations: [citation("chunk-1")] })];
  assert.equal(findHighlightQuestion(thread, "chunk-unknown"), null);
});

test("source excerpts are whitespace-normalized and shortened on a word boundary", () => {
  assert.equal(formatCitationExcerpt("Real\n lease   text", 40), "Real lease text");
  const excerpt = formatCitationExcerpt("A real source excerpt containing several words from the lease itself.", 36);
  assert.equal(excerpt, "A real source excerpt containing…");
});
