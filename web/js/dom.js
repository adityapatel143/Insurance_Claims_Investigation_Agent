// Minimal DOM helpers. Text is always set via textContent; no HTML strings are parsed.

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (name === "class") node.className = value;
    else if (name.startsWith("on") && typeof value === "function") node.addEventListener(name.slice(2), value);
    else node.setAttribute(name, value === true ? "" : String(value));
  }
  for (const child of children.flat()) {
    if (child === undefined || child === null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export const $ = (selector, root = document) => root.querySelector(selector);

export function clear(node) {
  node.replaceChildren();
  return node;
}

export function formatTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

export function toast(message, kind = "info") {
  const host = $("#toasts");
  const item = el("div", { class: `toast toast-${kind}`, role: kind === "error" ? "alert" : "status" }, message);
  host.append(item);
  setTimeout(() => item.remove(), kind === "error" ? 9000 : 4500);
}
