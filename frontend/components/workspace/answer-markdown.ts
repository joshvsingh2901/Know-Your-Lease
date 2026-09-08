import { createElement, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";

export function safeMarkdownUrl(value: string): string {
  if (value.startsWith("/") && !value.startsWith("//")) return value;
  if (value.startsWith("#")) return value;

  try {
    const url = new URL(value);
    return ["http:", "https:", "mailto:"].includes(url.protocol) ? value : "";
  } catch {
    return "";
  }
}

const components: Components = {
  p: ({ children }) => createElement("p", null, children),
  ol: ({ children }) => createElement("ol", null, children),
  ul: ({ children }) => createElement("ul", null, children),
  li: ({ children }) => createElement("li", null, children),
  strong: ({ children }) => createElement("strong", null, children),
  em: ({ children }) => createElement("em", null, children),
  h1: ({ children }) => createElement("h3", null, children),
  h2: ({ children }) => createElement("h3", null, children),
  h3: ({ children }) => createElement("h3", null, children),
  h4: ({ children }) => createElement("h4", null, children),
  a: ({ children, href }) => {
    const safeHref = href ? safeMarkdownUrl(href) : "";
    if (!safeHref) return createElement("span", null, children);
    const isExternal = safeHref.startsWith("http://") || safeHref.startsWith("https://");
    return createElement(
      "a",
      isExternal ? { href: safeHref, target: "_blank", rel: "noreferrer noopener" } : { href: safeHref },
      children,
    );
  },
};

export function AnswerMarkdown({ children }: { children: string }): ReactNode {
  return createElement(
    "div",
    { className: "lease-answer-markdown" },
    createElement(ReactMarkdown, { components, skipHtml: true, urlTransform: safeMarkdownUrl }, children),
  );
}
