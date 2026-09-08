import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const source = readFileSync(fileURLToPath(new URL("../app/page.tsx", import.meta.url)), "utf8");

function countLinkTo(href, label) {
  const pattern = new RegExp(`<Link[^>]*href="${href}"[^>]*>[\\s\\S]*?${label}[\\s\\S]*?</Link>`, "g");
  return (source.match(pattern) ?? []).length;
}

test("every Get started CTA on the landing page navigates to /documents", () => {
  assert.equal(countLinkTo("/documents", "Get started"), 3, "expected the header, hero, and closing CTAs");
});

test("the old #get-started scroll target no longer exists anywhere on the page", () => {
  assert.equal(source.includes("#get-started"), false);
  assert.equal(source.includes('id="get-started"'), false);
});

test("a visible Documents link navigates to /documents", () => {
  assert.ok(countLinkTo("/documents", "Documents") >= 1, "expected at least one Documents navigation link");
});

test("the old inline upload/Q&A flow is not referenced on the homepage", () => {
  assert.equal(source.includes("LeaseUpload"), false);
  assert.equal(source.includes("AuthGate"), false);
});

test("the approved landing sections remain", () => {
  assert.ok(source.includes("<HeroIllustration"), "hero illustration should remain");
  assert.ok(source.includes("<ProductDemo"), "product showcase should remain");
  assert.ok(source.includes('id="close"'), "closing section should remain");
  assert.ok(source.includes("<footer"), "footer should remain");
});

test("the landing page copy contains no em dashes", () => {
  assert.equal(/—/.test(source), false);
});
