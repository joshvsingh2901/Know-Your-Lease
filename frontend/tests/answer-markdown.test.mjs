import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

const { AnswerMarkdown, safeMarkdownUrl } = await import(
  "../components/workspace/answer-markdown.ts"
);

function render(markdown) {
  return renderToStaticMarkup(createElement(AnswerMarkdown, null, markdown));
}

test("answer Markdown renders numbered points as separate list items", () => {
  const html = render(`1. **General pet rules:** Written consent is required.
2. **Common areas:** Pets must be supervised.
3. **Fish tanks:** The size limit still applies.`);

  assert.match(html, /<ol>/);
  assert.equal((html.match(/<li>/g) ?? []).length, 3);
  assert.equal((html.match(/<strong>/g) ?? []).length, 3);
  assert.equal(html.includes("**General pet rules:**"), false);
});

test("answer Markdown supports emphasis without allowing raw HTML", () => {
  const html = render("A *careful* answer. <script>alert('no')</script>");

  assert.match(html, /<em>careful<\/em>/);
  assert.equal(html.includes("<script>"), false);
  assert.match(html, /alert\(&#x27;no&#x27;\)/);
});

test("answer Markdown allows ordinary web links and rejects script URLs", () => {
  assert.equal(safeMarkdownUrl("https://example.com/lease"), "https://example.com/lease");
  assert.equal(safeMarkdownUrl("/documents/123"), "/documents/123");
  assert.equal(safeMarkdownUrl("javascript:alert(1)"), "");
  assert.equal(safeMarkdownUrl("//evil.example.com"), "");
});
