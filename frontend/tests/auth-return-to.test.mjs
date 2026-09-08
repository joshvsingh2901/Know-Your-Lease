import assert from "node:assert/strict";
import test from "node:test";

const { readReturnTo, writeReturnTo } = await import("../lib/auth.ts");

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

test("an unauthenticated visit to /documents returns there after sign-in", () => {
  const storage = createStorage();
  writeReturnTo(storage, "/documents");
  assert.equal(readReturnTo(storage), "/documents");
});

test("returning to a specific document workspace is preserved through sign-in", () => {
  const storage = createStorage();
  writeReturnTo(storage, "/documents/c32cdd70-861d-4168-ae7f-5927549b8502");
  assert.equal(readReturnTo(storage), "/documents/c32cdd70-861d-4168-ae7f-5927549b8502");
});

test("the remembered destination is consumed once, not replayed on a later read", () => {
  const storage = createStorage();
  writeReturnTo(storage, "/documents");
  assert.equal(readReturnTo(storage), "/documents");
  assert.equal(readReturnTo(storage), "/");
});

test("nothing remembered falls back to the landing page", () => {
  const storage = createStorage();
  assert.equal(readReturnTo(storage), "/");
});

test("an external or malformed value never redirects off-site", () => {
  const storage = createStorage();
  writeReturnTo(storage, "https://evil.example.com/phish");
  assert.equal(readReturnTo(storage), "/");
});
