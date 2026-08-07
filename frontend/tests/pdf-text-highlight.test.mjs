import assert from "node:assert/strict";
import test from "node:test";

const { highlightCitationSnippet, normalizePdfText } = await import(
  "../lib/pdf-text-highlight.ts"
);

class FakeSpan {
  constructor(text) {
    this.textContent = text;
    this.attributes = new Map();
  }

  setAttribute(name, value) {
    this.attributes.set(name, value);
  }

  removeAttribute(name) {
    this.attributes.delete(name);
  }

  hasAttribute(name) {
    return this.attributes.has(name);
  }
}

class FakeTextLayer {
  constructor(spans) {
    this.spans = spans;
  }

  querySelectorAll(selector) {
    if (selector.includes("[data-citation-highlight]")) {
      return this.spans.filter((span) => span.hasAttribute("data-citation-highlight"));
    }
    return this.spans;
  }
}

test("a normalized citation snippet highlights only its matching text spans", () => {
  const spans = [
    new FakeSpan("The Tenant agrees to not allow pets"),
    new FakeSpan(" in suite common areas."),
    new FakeSpan("Garbage must be bagged."),
  ];
  const layer = new FakeTextLayer(spans);

  const matched = highlightCitationSnippet(
    layer,
    "The Tenant agrees to not allow pets\n in suite common areas.",
  );

  assert.equal(matched, true);
  assert.equal(spans[0].hasAttribute("data-citation-highlight"), true);
  assert.equal(spans[1].hasAttribute("data-citation-highlight"), true);
  assert.equal(spans[2].hasAttribute("data-citation-highlight"), false);
  assert.equal(normalizePdfText("Pets  in\ncommon areas"), "petsincommonareas");
});

test("a failed text match clears the previous highlight and preserves page fallback", () => {
  const spans = [new FakeSpan("Pets must be kept on a leash.")];
  const layer = new FakeTextLayer(spans);

  assert.equal(
    highlightCitationSnippet(layer, "Pets must be kept on a leash."),
    true,
  );
  assert.equal(
    highlightCitationSnippet(layer, "A clause not present in the PDF."),
    false,
  );
  assert.equal(spans[0].hasAttribute("data-citation-highlight"), false);
});
