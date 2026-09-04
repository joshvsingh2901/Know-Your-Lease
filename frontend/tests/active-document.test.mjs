import assert from "node:assert/strict";
import test from "node:test";

const {
  ACTIVE_DOCUMENT_STORAGE_KEY,
  clearActiveDocumentId,
  readActiveDocumentId,
  restoreActiveDocument,
  saveActiveDocumentId,
  shouldPollDocumentStatus,
} = await import("../lib/active-document.ts");

function createStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem(key) {
      return values.get(key) ?? null;
    },
    removeItem(key) {
      values.delete(key);
    },
    setItem(key, value) {
      values.set(key, value);
    },
  };
}

function documentWith(status) {
  return {
    id: "472ae957-3f21-4780-84a8-7841e7b1678b",
    filename: "lease.pdf",
    status,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    error_message: null,
  };
}

test("a ready document restores after refresh", async () => {
  const storage = createStorage({ [ACTIVE_DOCUMENT_STORAGE_KEY]: "ready-document" });
  const restored = await restoreActiveDocument(storage, async (documentId) => {
    assert.equal(documentId, "ready-document");
    return documentWith("ready");
  });

  assert.equal(restored?.status, "ready");
  assert.equal(readActiveDocumentId(storage), "ready-document");
});

test("a processing document restores and resumes status polling", async () => {
  const storage = createStorage({ [ACTIVE_DOCUMENT_STORAGE_KEY]: "processing-document" });
  const restored = await restoreActiveDocument(storage, async () => documentWith("processing"));

  assert.equal(restored?.status, "processing");
  assert.equal(shouldPollDocumentStatus(restored.status), true);
});

test("a queued document resumes status polling", () => {
  assert.equal(shouldPollDocumentStatus("queued"), true);
});

test("an invalid or deleted document clears saved state", async () => {
  const storage = createStorage({ [ACTIVE_DOCUMENT_STORAGE_KEY]: "deleted-document" });
  const restored = await restoreActiveDocument(storage, async () => {
    throw { status: 404 };
  });

  assert.equal(restored, null);
  assert.equal(readActiveDocumentId(storage), null);
});

test("an invalid saved document ID clears saved state", async () => {
  const storage = createStorage({ [ACTIVE_DOCUMENT_STORAGE_KEY]: "not-a-document-id" });
  const restored = await restoreActiveDocument(storage, async () => {
    throw { status: 422 };
  });

  assert.equal(restored, null);
  assert.equal(readActiveDocumentId(storage), null);
});

test("a failed document clears saved state during restore", async () => {
  const storage = createStorage({ [ACTIVE_DOCUMENT_STORAGE_KEY]: "failed-document" });
  const restored = await restoreActiveDocument(storage, async () => documentWith("failed"));

  assert.equal(restored, null);
  assert.equal(readActiveDocumentId(storage), null);
});

test("an expired session (401) does not clear the saved document ID", async () => {
  const storage = createStorage({ [ACTIVE_DOCUMENT_STORAGE_KEY]: "my-document" });

  await assert.rejects(
    () =>
      restoreActiveDocument(storage, async () => {
        throw { status: 401 };
      }),
    (error) => error.status === 401,
  );

  assert.equal(readActiveDocumentId(storage), "my-document");
});

test("another user's document (404) still clears saved state", async () => {
  const storage = createStorage({ [ACTIVE_DOCUMENT_STORAGE_KEY]: "someone-elses-document" });

  const restored = await restoreActiveDocument(storage, async () => {
    throw { status: 404 };
  });

  assert.equal(restored, null);
  assert.equal(readActiveDocumentId(storage), null);
});

test("upload another lease clears saved state", () => {
  const storage = createStorage();
  saveActiveDocumentId(storage, "active-document");
  clearActiveDocumentId(storage);

  assert.equal(readActiveDocumentId(storage), null);
});
