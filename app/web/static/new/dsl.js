// DSL compiler for kerangka teori. Pure (DOM-free) so it is unit-testable under
// node:test. parseDSL is the source-of-truth reader; dslToDot emits Graphviz DOT.

const KINDS = new Set(["diteliti", "latar", "latar*"]);

// Deterministic id from a label: keep [A-Za-z0-9], map everything else to its
// code point in hex. Shared by DOT emission AND badge overlay so ids round-trip.
export function slug(label) {
  let out = "";
  for (const ch of String(label)) {
    out += /[A-Za-z0-9]/.test(ch) ? ch : "_" + ch.codePointAt(0).toString(16);
  }
  return out || "_empty";
}

function dotEscape(label) {
  return String(label).replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/[\r\n]+/g, " ");
}

// Resolve edge type from arrow + optional ": reltype". Returns {type} or {error}.
function resolveEdge(arrow, suffix) {
  const rel = (suffix || "").trim().toLowerCase();
  if (arrow === "-|") {
    if (rel === "memicu") return { error: "kontradiksi: -| tidak boleh : memicu" };
    return { type: "menghambat" };
  }
  // arrow === "->"
  if (rel === "menghambat") return { type: "menghambat" };
  return { type: "memicu" };
}

export function parseDSL(text) {
  const nodes = new Map();   // label -> {label, kind, implicit}
  const edges = [];
  const errors = [];

  const ensure = (label, kind, implicit) => {
    label = label.trim();
    if (!label) return;
    const existing = nodes.get(label);
    if (existing) {
      // Explicit decl upgrades an implicit node's kind.
      if (!implicit) { existing.kind = kind; existing.implicit = false; }
      return;
    }
    nodes.set(label, { label, kind, implicit: !!implicit });
  };

  const lines = String(text || "").split(/\r?\n/);
  lines.forEach((raw, i) => {
    const lineNo = i + 1;
    const line = raw.trim();
    if (!line || line.startsWith("#")) return;

    // Node decl: starts with "[kind]".
    if (line.startsWith("[")) {
      const close = line.indexOf("]");
      if (close === -1) {
        errors.push({ line: lineNo, col: 1, msg: "kurung ']' tidak ditemukan" });
        return;
      }
      const kind = line.slice(1, close).trim();
      const label = line.slice(close + 1).trim();
      if (!KINDS.has(kind)) {
        errors.push({ line: lineNo, col: 2, msg: `jenis node tidak dikenal: ${kind}` });
        return;
      }
      if (!label) {
        errors.push({ line: lineNo, col: close + 2, msg: "label node kosong" });
        return;
      }
      ensure(label, kind, false);
      return;
    }

    // Edge decl: "<label> <arrow> <label> [: reltype]".
    const arrowIdx = line.search(/->|-\|/);
    if (arrowIdx === -1) {
      errors.push({ line: lineNo, col: 1, msg: "baris bukan node maupun panah" });
      return;
    }
    const arrow = line.substr(arrowIdx, 2);
    const from = line.slice(0, arrowIdx).trim();
    let rest = line.slice(arrowIdx + 2).trim();
    let suffix = "";
    const colon = rest.lastIndexOf(":");
    if (colon !== -1) {
      suffix = rest.slice(colon + 1);
      rest = rest.slice(0, colon).trim();
    }
    const to = rest.trim();
    if (!from || !to) {
      errors.push({ line: lineNo, col: 1, msg: "panah perlu label asal dan tujuan" });
      return;
    }
    const resolved = resolveEdge(arrow, suffix);
    if (resolved.error) {
      errors.push({ line: lineNo, col: arrowIdx + 1, msg: resolved.error });
      return;
    }
    ensure(from, "latar", true);
    ensure(to, "latar", true);
    edges.push({ from, to, type: resolved.type });
  });

  return { nodes: [...nodes.values()], edges, errors };
}

export function dslToDot(parsed, citations = {}) {
  const lines = [
    "digraph G {",
    '  rankdir=TB;',
    '  node [shape=box, fontname="Inter"];',
  ];
  for (const n of parsed.nodes) {
    const id = `id="node-${slug(n.label)}"`;
    let style;
    if (n.kind === "diteliti") {
      style = `penwidth=2.5, style=solid`;
    } else {
      style = `style=dashed, color="#999", fontcolor="#555"`;
    }
    lines.push(`  "${dotEscape(n.label)}" [${style}, ${id}];`);
  }
  for (const e of parsed.edges) {
    const attrs = e.type === "menghambat"
      ? 'color="#2c5fa8", arrowhead=diamond'
      : 'color="#c0392b"';
    lines.push(`  "${dotEscape(e.from)}" -> "${dotEscape(e.to)}" [${attrs}];`);
  }
  lines.push("}");
  return lines.join("\n");
}
