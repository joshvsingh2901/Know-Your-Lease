import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const panelSource = readFileSync(
  fileURLToPath(new URL("../components/workspace/workspace-ask-panel.tsx", import.meta.url)),
  "utf8",
);
const globalStyles = readFileSync(
  fileURLToPath(new URL("../app/globals.css", import.meta.url)),
  "utf8",
);

test("every mapped suggestion uses the shared refined interaction class", () => {
  assert.match(panelSource, /SUGGESTIONS\.map[\s\S]*className="lease-question-suggestion"/);
  assert.match(panelSource, /className="lease-question-suggestion-action"/);
});

test("suggestion hover and keyboard focus change paint only, without layout shift", () => {
  assert.match(globalStyles, /\.lease-question-suggestion:hover/);
  assert.match(globalStyles, /\.lease-question-suggestion:focus-visible/);
  assert.match(globalStyles, /transition:[\s\S]*border-color 150ms ease/);
  assert.doesNotMatch(globalStyles, /\.lease-question-suggestion\s*\{[^}]*transition:\s*all/);
  assert.doesNotMatch(globalStyles, /\.lease-question-suggestion:hover\s*\{[^}]*(?:margin|padding|border-width|box-shadow)/);
});
