import assert from "node:assert/strict";
import test from "node:test";

const { shouldEnterWorkspace } = await import("../components/documents/upload-navigation.ts");

test("enters the workspace when the session's own upload becomes ready", () => {
  assert.equal(shouldEnterWorkspace("doc-1", "doc-1", "ready"), true);
});

test("does not enter the workspace while the session's own upload is still processing", () => {
  assert.equal(shouldEnterWorkspace("doc-1", "doc-1", "processing"), false);
  assert.equal(shouldEnterWorkspace("doc-1", "doc-1", "queued"), false);
  assert.equal(shouldEnterWorkspace("doc-1", "doc-1", "uploaded"), false);
});

test("does not enter the workspace when the session's own upload fails", () => {
  assert.equal(shouldEnterWorkspace("doc-1", "doc-1", "failed"), false);
});

test("never navigates for an unrelated document reaching ready in the background", () => {
  assert.equal(shouldEnterWorkspace("doc-1", "doc-2", "ready"), false);
});

test("does nothing once no upload is being tracked in this session", () => {
  assert.equal(shouldEnterWorkspace(null, "doc-1", "ready"), false);
});
