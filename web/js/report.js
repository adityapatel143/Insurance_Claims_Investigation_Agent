// Render an InvestigationResult (advisory output) with DOM nodes only.
import { el } from "./dom.js";

const list = (items, render) =>
  items?.length ? el("ul", { class: "plain-list" }, items.map((item) => el("li", {}, render(item)))) : el("p", { class: "muted" }, "None.");

const refs = (ids) => (ids?.length ? el("div", { class: "refs" }, ids.map((id) => el("code", {}, id))) : null);

const pct = (value) => (typeof value === "number" ? `${Math.round(value * 100)}%` : "-");

function section(title, body) {
  return el("section", { class: "report-section" }, el("h4", {}, title), body);
}

export function renderReport(report) {
  const level = (value) => el("span", { class: `badge badge-${String(value).toLowerCase()}` }, value);
  return el(
    "div",
    { class: "report" },
    el(
      "div",
      { class: "report-header" },
      el("span", { class: `status status-${report.status}` }, report.status),
      el("span", {}, `Confidence ${pct(report.confidence)}`),
      report.human_review_required ? el("span", { class: "badge badge-high" }, "Human review required") : null,
    ),
    section("Executive summary", el("p", {}, report.executive_summary ?? "-")),
    section(
      "Review reasons",
      report.review_reasons?.length ? el("div", { class: "refs" }, report.review_reasons.map((r) => el("code", {}, r))) : el("p", { class: "muted" }, "None."),
    ),
    section(
      "Potential anomaly signals (require review)",
      list(report.anomaly_signals, (s) => [
        el("strong", {}, s.code), ` (${s.origin ?? "-"}, confidence ${pct(s.confidence)}): `, s.description,
        refs(s.evidence_refs),
        s.limitations?.length ? el("div", { class: "muted small" }, `Limitations: ${s.limitations.join("; ")}`) : null,
      ]),
    ),
    section(
      "Risk indicators",
      list(report.risk_indicators, (r) => [level(r.level), " ", el("strong", {}, r.category), `: ${r.rationale}`, refs(r.evidence_refs)]),
    ),
    section("Missing information", list(report.missing_information, (m) => [el("strong", {}, m.item), `: ${m.reason}`, refs(m.related_evidence_ids)])),
    section(
      "Recommended analyst actions",
      list(report.recommended_analyst_actions, (a) => [level(a.priority), " ", el("strong", {}, a.action), ` - ${a.rationale}`, refs(a.evidence_refs)]),
    ),
    section(
      "Evidence",
      list(report.evidence_summary, (e) => [el("code", {}, e.evidence_id), ` ${e.description} `, el("span", { class: "muted small" }, `(${e.source}, ${e.locator})`)]),
    ),
    section(
      "Retrieved guidance and examples",
      list(report.retrieved_sources, (s) => [el("strong", {}, s.title ?? s.source_id), ` ${s.source_type ?? ""} `, el("code", {}, s.source_id)]),
    ),
    section("Limitations", list(report.limitations, (l) => l)),
  );
}
