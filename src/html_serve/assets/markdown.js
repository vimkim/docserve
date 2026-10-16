// The viewer and checker share Markdown recognition, source locations, and math.
import { Marked, gfmHeadingId } from "./vendor/markdown.js";

export function mermaidOptions(theme = "light") {
  return {
    startOnLoad: false, securityLevel: "strict",
    theme: theme === "dark" ? "dark" : "default", suppressErrorRendering: true,
  };
}

// Container token text removes list/quote prefixes but retains source lines.
// Locate each raw token within its parent, so repeated fences inside ordinary
// code or HTML cannot steal the location of a rendered Mermaid diagram.
function locate(tokens, source, firstLine = 1) {
  let cursor = 0;
  for (const token of tokens) {
    if (token.type === "checkbox") continue;
    const raw = token.raw.replace(/^\[[ xX]\] /, "");
    const start = source.indexOf(raw, cursor);
    if (start < 0) throw new Error("Could not locate Markdown token in its source");
    token.sourceLine = firstLine + source.slice(0, start).split("\n").length - 1;
    cursor = start + raw.length;
    if (token.type === "blockquote") locate(token.tokens, token.text, token.sourceLine);
    if (token.type === "list") {
      let offset = 0;
      for (const item of token.items) {
        const start = token.raw.indexOf(item.raw, offset);
        const line = token.sourceLine + token.raw.slice(0, start).split("\n").length - 1;
        locate(item.tokens, item.text, line);
        offset = start + item.raw.length;
      }
    }
  }
}

export async function parseMarkdown(source, slot, { locations = false } = {}) {
  const parser = new Marked({ gfm: true, breaks: false });
  parser.use(gfmHeadingId());
  parser.use({
    renderer: { code(token) {
      return token.lang?.split(/\s+/)[0].toLowerCase() === "mermaid"
        ? slot("mermaid", token) : false;
    } },
  });
  if (locations) parser.use({
    tokenizer: { def(source) {
      const token = parser.Tokenizer.prototype.def.call(this, source);
      // Retain duplicate definitions as empty-output tokens. Otherwise Marked
      // discards their raw spans, and a fenced example inside a discarded
      // multiline title can steal the location of the next diagram. A Symbol
      // keeps the first definition's link target and cannot match author text.
      if (token && Object.hasOwn(this.lexer.tokens.links, token.tag)) token.tag = Symbol(token.tag);
      return token || false;
    } },
    hooks: { processAllTokens(tokens) {
      locate(tokens, source.replace(/\r\n?/g, "\n"));
      return tokens;
    } },
  });
  let math;
  if (source.includes("$")) {
    math = await import("./vendor/math.js");
    const extension = math.markedKatex();
    for (const rule of extension.extensions) {
      rule.renderer = (token) => slot("math", token);
    }
    parser.use(extension);
  }
  return { html: parser.parse(source), math };
}
