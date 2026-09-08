import assert from "node:assert/strict";
import test from "node:test";

const { highlightCitationSnippet, mergeHighlightRectangles, normalizePdfText } = await import(
  "../lib/pdf-text-highlight.ts"
);

class FakeSpan {
  constructor(text, { classes = [], children = [], childNodes = [], ownerDocument = null } = {}) {
    this.textContent = text;
    this.attributes = new Map();
    this.children = children;
    this.childNodes = childNodes;
    this.ownerDocument = ownerDocument;
    this.classList = { contains: (name) => classes.includes(name) };
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

  querySelector(selector) {
    return selector === "span" ? (this.children[0] ?? null) : null;
  }
}

class FakeTextLayer {
  constructor(spans, overlayLayer = null) {
    this.spans = spans;
    this.overlayLayer = overlayLayer;
  }

  querySelectorAll(selector) {
    if (selector.includes("[data-citation-highlight]")) {
      return this.spans.filter((span) => span.hasAttribute("data-citation-highlight"));
    }
    return this.spans;
  }

  querySelector() {
    return this.overlayLayer;
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

test("tagged-PDF markedContent wrappers are ignored so leaf spans remain visible", () => {
  const first = new FakeSpan("A tenancy agreement cannot prohibit animals ");
  const second = new FakeSpan("in or around the residential building.");
  const wrapper = new FakeSpan(`${first.textContent}${second.textContent}`, {
    classes: ["markedContent"],
    children: [first, second],
  });
  const layer = new FakeTextLayer([wrapper, first, second]);

  assert.equal(
    highlightCitationSnippet(
      layer,
      "A tenancy agreement cannot prohibit animals in or around the residential building.",
    ),
    true,
  );
  assert.equal(wrapper.hasAttribute("data-citation-highlight"), false);
  assert.equal(first.hasAttribute("data-citation-highlight"), true);
  assert.equal(second.hasAttribute("data-citation-highlight"), true);
});

test("an in-span match renders only the cited character range", () => {
  const selectedOffsets = {};
  const textNode = { nodeType: 3 };
  const overlays = [];
  const overlayLayer = {
    replaceChildren() {
      overlays.length = 0;
    },
    getBoundingClientRect() {
      return { left: 0, top: 0 };
    },
    append(overlay) {
      overlays.push(overlay);
    },
  };
  const ownerDocument = {
    createRange() {
      return {
        setStart(node, offset) {
          selectedOffsets.start = offset;
        },
        setEnd(node, offset) {
          selectedOffsets.end = offset;
        },
        getClientRects() {
          return [{ left: 10, top: 20, width: 160, height: 14 }];
        },
      };
    },
    createElement() {
      return { style: {}, setAttribute() {} };
    },
  };
  overlayLayer.ownerDocument = ownerDocument;
  const leadingText = "Pets are allowed after registration. ";
  const citationText = "Every animal must remain on a leash.";
  const span = new FakeSpan(`${leadingText}${citationText}`, {
    childNodes: [textNode],
    ownerDocument,
  });
  const layer = new FakeTextLayer([span], overlayLayer);

  assert.equal(highlightCitationSnippet(layer, citationText), true);
  assert.equal(selectedOffsets.start, leadingText.length);
  assert.equal(selectedOffsets.end, leadingText.length + citationText.length - 1);
  assert.equal(overlays.length, 1);
});

test("adjacent matched rectangles merge by line without bridging a large gap", () => {
  assert.deepEqual(
    mergeHighlightRectangles([
      { left: 10, top: 20, width: 30, height: 12 },
      { left: 43, top: 20.5, width: 40, height: 12 },
      { left: 120, top: 20, width: 24, height: 12 },
      { left: 10, top: 39, width: 70, height: 12 },
    ]),
    [
      { left: 10, top: 20, width: 73, height: 12.5 },
      { left: 120, top: 20, width: 24, height: 12 },
      { left: 10, top: 39, width: 70, height: 12 },
    ],
  );
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

test("citation matching tolerates PDF punctuation and a truncated excerpt ellipsis", () => {
  const spans = [
    new FakeSpan("Fish tanks (up to 20 gallons) are permitted; larger tanks require consent."),
  ];
  const layer = new FakeTextLayer(spans);

  assert.equal(
    highlightCitationSnippet(layer, "Fish tanks up to 20 gallons are permitted…"),
    true,
  );
  assert.equal(spans[0].hasAttribute("data-citation-highlight"), true);
});

test("citation matching highlights a trustworthy phrase when extraction adds extra words", () => {
  const spans = [
    new FakeSpan("Rent is to be paid on the first day of each month."),
  ];
  const layer = new FakeTextLayer(spans);

  assert.equal(
    highlightCitationSnippet(layer, "Rent is to be paid on the first day of each calendar month."),
    true,
  );
  assert.equal(spans[0].hasAttribute("data-citation-highlight"), true);
});

test("citation matching rejects a short generic overlap and ambiguous repeated passage", () => {
  const generic = new FakeSpan("The tenant agrees to keep the unit clean.");
  const duplicated = new FakeSpan(
    "Pets must remain on leash. Other text. Pets must remain on leash.",
  );
  const layer = new FakeTextLayer([generic, duplicated]);

  assert.equal(
    highlightCitationSnippet(
      layer,
      "The tenant agrees to keep the unit clean and report every serious repair to management promptly.",
    ),
    false,
  );
  assert.equal(
    highlightCitationSnippet(layer, "Pets must remain on leash."),
    false,
  );
  assert.equal(generic.hasAttribute("data-citation-highlight"), false);
  assert.equal(duplicated.hasAttribute("data-citation-highlight"), false);
});
