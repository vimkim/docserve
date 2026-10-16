import { mermaidOptions, parseMarkdown } from "./markdown.js";

export async function collect(source) {
  const diagrams = [];
  await parseMarkdown(source, (kind, token) => {
    if (kind === "mermaid") {
      diagrams.push({ index: diagrams.length + 1, line: token.sourceLine, source: token.text });
    }
    return "";
  }, { locations: true });
  return diagrams;
}

export async function syntax(diagrams) {
  if (!diagrams.length) return [];
  const mermaid = (await import("./vendor/mermaid.js")).default;
  mermaid.initialize(mermaidOptions());
  const results = [];
  for (const diagram of diagrams) {
    try {
      await mermaid.parse(diagram.source);
      results.push({ status: "passed", message: null });
    } catch (error) {
      results.push({ status: "failed", message: String(error.message || error) });
    }
  }
  return results;
}

export async function rendered() {
  const { diagramState } = await import("./viewer.js");
  const state = await diagramState();
  return { error: state.error, diagrams: state.elements.map((element) => {
    const error = element.querySelector(":scope > .render-error > summary");
    const svg = element.querySelector("svg");
    const visible = svg && svg.getBoundingClientRect().width > 0 && svg.getBoundingClientRect().height > 0;
    return {
      status: !error && visible ? "passed" : "failed",
      message: error?.textContent || (visible ? null : "Viewer did not produce a visible SVG"),
    };
  }) };
}
