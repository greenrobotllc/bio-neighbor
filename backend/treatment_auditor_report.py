"""
Treatment Auditor PDF report builder (issue #67).

Single source of truth for the audit report's HTML+CSS — both the Python CLI
(`treatment_auditor_cli.py --pdf`) and the macOS app
(`TreatmentAuditReportClient` in the Swift sources) POST a `ReportPayload`
here and write the response bytes to disk. WeasyPrint renders the HTML to a
paginated PDF — `@page`, `page-break-after: avoid`, `page-break-inside: avoid`,
table styling, and severity chips are supported natively, so the layout
behaves identically across both clients.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import weasyprint

REPO_URL = "https://github.com/greenrobotllc/bio-neighbor"

# Five-entity HTML escape — &, <, >, ", ' — applied in this order so output
# is byte-equivalent regardless of input order.
def _escape(s: Any) -> str:
    text = "" if s is None else str(s)
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&#39;")
    return text


def _paragraphs(text: Optional[str]) -> str:
    """Swift `paragraphs(from:)` — split on blank lines, escape, preserve
    intra-paragraph newlines as <br>. Empty input returns "" (caller decides
    whether to render a placeholder)."""
    if not text:
        return ""
    chunks = [c.strip() for c in text.split("\n\n")]
    chunks = [c for c in chunks if c]
    if not chunks:
        return ""
    return "".join(f"<p>{_escape(c).replace(chr(10), '<br>')}</p>" for c in chunks)


def _format_count(n: Any) -> str:
    """Swift `Int.formatted()` defaults to en-US grouping (1,234)."""
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


def _iso_timestamp(dt_str: Optional[str]) -> str:
    """Accept either an ISO-8601 string (preferred — clients send what they
    have) or fall back to "now". Always returns a printable string."""
    if dt_str:
        return dt_str
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_FILENAME_KEEP = re.compile(r"[^a-z0-9]+")


def default_filename(report: Dict[str, Any]) -> str:
    """Mirror Swift `defaultFilename(for:)` — `treatment-audit-<slug>-<stamp>.pdf`."""
    plan = report.get("plan") or {}
    raw = plan.get("subtype_display") or plan.get("subtype") or plan.get("cancer_type_display") or plan.get("cancer_type") or ""
    slug = _FILENAME_KEEP.sub("-", raw.lower()).strip("-")
    base = slug or "audit"
    generated_at = report.get("generated_at") or ""
    stamp = ""
    try:
        # Strip trailing 'Z' for fromisoformat (Python <3.11 doesn't accept it).
        clean = generated_at.replace("Z", "+00:00") if generated_at else ""
        if clean:
            stamp = datetime.fromisoformat(clean).strftime("%Y%m%d-%H%M")
    except ValueError:
        stamp = ""
    if not stamp:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return f"treatment-audit-{base}-{stamp}.pdf"


# Print stylesheet for the audit report. Every rule below is supported by
# WeasyPrint as-is; do not modify without rendering a sample PDF for review.
STYLESHEET = """
@page { margin: 0.6in; }
body { font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
       font-size: 11pt; color: #1c1c1c; line-height: 1.45; margin: 0; padding: 0; }
.report-header { border-bottom: 2px solid #333; padding-bottom: 8pt; margin-bottom: 14pt; }
.report-header h1 { font-size: 20pt; margin: 0 0 4pt 0; }
h2 { font-size: 13.5pt; margin-top: 18pt; margin-bottom: 8pt;
     border-bottom: 1px solid #999; padding-bottom: 3pt;
     page-break-after: avoid; }
h3 { font-size: 11.5pt; margin-top: 14pt; margin-bottom: 6pt; page-break-after: avoid; }
p { margin: 6pt 0; }
.muted { color: #666; font-size: 9.5pt; }
.section { page-break-inside: auto; margin-bottom: 6pt; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0; font-size: 10.5pt; }
table.kv th { width: 28%; text-align: left; background: #f4f4f4;
              padding: 5pt 8pt; border-bottom: 1px solid #ddd;
              vertical-align: top; font-weight: 600; }
table.kv td { padding: 5pt 8pt; border-bottom: 1px solid #ddd; vertical-align: top; }
table.data th, table.data td { text-align: left; padding: 5pt 8pt;
                                border-bottom: 1px solid #ddd; vertical-align: top; }
table.data th { background: #f4f4f4; font-weight: 600; }
ul, ol { padding-left: 22pt; margin: 6pt 0; }
ul.plain { list-style: none; padding-left: 0; }
ul.plain > li { margin: 3pt 0; }
ul.references { margin-top: 4pt; padding-left: 18pt; }
ul.references li { margin: 2pt 0; }
code { font-family: ui-monospace, "SF Mono", Menlo, monospace;
       font-size: 9.5pt; background: #f4f4f4; padding: 1pt 4pt;
       border-radius: 3pt; }
a { color: #1a5fb4; word-break: break-all; }
.disclaimer { background: #fff8e1; border: 1px solid #f0c83a;
              padding: 8pt 12pt; border-radius: 4pt; margin: 10pt 0;
              font-size: 10.5pt; }
.summary-block { background: #f6f9ff; border-left: 3px solid #4070d0;
                 padding: 8pt 12pt; margin: 10pt 0;
                 page-break-inside: avoid; }
.summary-block .label { font-weight: 600; font-size: 10.5pt;
                        margin-bottom: 4pt; color: #2c5aaf; }
.prose p { margin: 6pt 0; }
.step-done { color: #1f7a1f; font-weight: 600; }
.step-skipped { color: #666; font-weight: 600; }
.step-failed { color: #b34d00; font-weight: 600; }
.step-running { color: #4070d0; font-weight: 600; }
.chip { display: inline-block; padding: 1pt 6pt; margin-left: 4pt;
        border-radius: 8pt; background: #eceff7; color: #4a4a4a;
        font-size: 9pt; }
.footer { margin-top: 24pt; padding-top: 8pt;
          border-top: 1px solid #ccc; font-size: 9.5pt; color: #555; }
.footer p { margin: 3pt 0; }
h4 { font-size: 10.5pt; margin-top: 10pt; margin-bottom: 4pt; page-break-after: avoid; }
.sev-severe, .sev-major { display: inline-block; padding: 1pt 6pt; border-radius: 3pt;
              background: #fdecec; color: #b00020; font-weight: 600; font-size: 9pt; }
.sev-moderate { display: inline-block; padding: 1pt 6pt; border-radius: 3pt;
                background: #fff4e0; color: #a55400; font-weight: 600; font-size: 9pt; }
.sev-minor { display: inline-block; padding: 1pt 6pt; border-radius: 3pt;
             background: #fff9d6; color: #806300; font-weight: 600; font-size: 9pt; }
.sev-unknown { display: inline-block; padding: 1pt 6pt; border-radius: 3pt;
               background: #eceff7; color: #4a4a4a; font-weight: 600; font-size: 9pt; }
"""


# --- section builders -------------------------------------------------------

def _row(label: str, value: str) -> str:
    return f"<tr><th>{_escape(label)}</th><td>{_escape(value)}</td></tr>"


def _row_raw(label: str, raw_value: str) -> str:
    return f"<tr><th>{_escape(label)}</th><td>{raw_value}</td></tr>"


def _header_section(timestamp: str) -> str:
    return (
        '<header class="report-header">'
        '<h1>Bio-Neighbor Treatment Auditor Report</h1>'
        f'<div class="muted">Generated {_escape(timestamp)}</div>'
        f'<div class="muted">Source: <a href="{REPO_URL}">{REPO_URL}</a></div>'
        '</header>'
    )


def _disclaimer_section() -> str:
    return (
        '<section class="disclaimer">'
        '<strong>Research tool only — not medical advice.</strong> '
        'This report compiles publicly available data from NCI PDQ and '
        'ClinicalTrials.gov plus on-device LLM summaries. Discuss any '
        'treatment-plan questions with your oncology team.'
        '</section>'
    )


def _inputs_section(plan: Dict[str, Any]) -> str:
    rows: List[str] = []
    rows.append(_row("Cancer type", plan.get("cancer_type_display") or plan.get("cancer_type") or ""))
    subtype = plan.get("subtype_display") or plan.get("subtype")
    if subtype:
        rows.append(_row("Subtype", subtype))
    markers = plan.get("subtype_markers") or []
    if markers:
        rows.append(_row("Markers", ", ".join(markers)))
    rows.append(_row("Stage", plan.get("stage") or "Unspecified"))
    detail = plan.get("stage_detail")
    if detail:
        rows.append(_row("Stage detail", detail))

    drugs = plan.get("drugs") or []
    if not drugs:
        rows.append(_row("Prescribed drugs", "(none)"))
    else:
        items = []
        for d in drugs:
            chembl = f" ({_escape(d['chembl_id'])})" if d.get("chembl_id") else ""
            items.append(f"<li>{_escape(d.get('name', ''))}{chembl}</li>")
        rows.append(_row_raw("Prescribed drugs", f'<ul class="plain">{"".join(items)}</ul>'))

    treatments = plan.get("treatments") or []
    if not treatments:
        rows.append(_row("Scheduled treatments", "(none)"))
    else:
        items = "".join(f"<li>{_escape(t)}</li>" for t in treatments)
        rows.append(_row_raw("Scheduled treatments", f'<ul class="plain">{items}</ul>'))

    symptoms = plan.get("symptoms") or []
    if not symptoms:
        rows.append(_row("Symptoms / side effects", "(none)"))
    else:
        items: List[str] = []
        for sym in symptoms:
            text = _escape(sym.get("text", ""))
            sev = sym.get("severity")
            if sev:
                items.append(f'<li>{text} <span class="chip">{_escape(sev)}</span></li>')
            else:
                items.append(f"<li>{text}</li>")
        rows.append(_row_raw("Symptoms / side effects", f'<ul class="plain">{"".join(items)}</ul>'))

    return (
        '<section class="section">'
        '<h2>1. Inputs</h2>'
        f'<table class="kv">{"".join(rows)}</table>'
        '</section>'
    )


def _severity_css_class(severity: Optional[str]) -> str:
    s = (severity or "").lower()
    # `major` (DDInter) and `severe` (legacy DrugBank) both map to red.
    if s in ("major", "severe"):
        return "sev-major"
    if s == "moderate":
        return "sev-moderate"
    if s == "minor":
        return "sev-minor"
    return "sev-unknown"


def _merges_block(merge_notes: List[Dict[str, Any]]) -> str:
    if not merge_notes:
        return ""
    rows = []
    for note in merge_notes:
        originals = " + ".join(_escape(n) for n in note.get("original_names") or [])
        ingredient = _escape(note.get("ingredient_name") or "")
        rows.append(f"<li>{originals} → <strong>{ingredient}</strong></li>")
    return (
        "<h3>Brand → generic dedupe (RxNorm)</h3>"
        "<p>The following input pairs collapsed onto a single ingredient "
        "via RxNorm normalization. Per-drug fetches downstream used the "
        "merged entry, so trial / interaction / overlap / FAERS results "
        "are not duplicated for the same active ingredient:</p>"
        f"<ul>{''.join(rows)}</ul>"
    )


def _interactions_block(report: Dict[str, Any]) -> str:
    interactions = report.get("drug_interactions") or []
    available = report.get("drug_interaction_data_available", True)
    if not interactions and available:
        return ""
    if not available:
        return (
            "<h3>Pairwise drug-drug interactions (DDInter)</h3>"
            '<p class="muted">'
            "DDInter hasn't been loaded into the local "
            "<code>drug_interactions</code> table on this install, so "
            "pairwise drug-drug interactions could not be checked. This "
            'is not the same as "no interactions found" — the audit '
            "cannot speak to interactions at all in this state. "
            "Run <code>python backend/load_ddinter_interactions.py</code> "
            "to fetch the eight ATC-class CSVs from "
            '<a href="https://ddinter.scbdd.com">ddinter.scbdd.com</a> '
            "(no registration required) and populate the table. "
            "DDInter is licensed CC BY-NC-SA 4.0 — non-commercial use only."
            "</p>"
        )
    rows = []
    for r in interactions:
        sev = r.get("severity") or "unknown"
        cls = _severity_css_class(r.get("severity"))
        rows.append(
            "<tr>"
            f"<td>{_escape(r.get('drug_a', ''))} ↔ {_escape(r.get('drug_b', ''))}</td>"
            f'<td><span class="{cls}">{_escape(sev.upper())}</span></td>'
            f"<td>{_escape(r.get('description') or '')}</td>"
            "</tr>"
        )
    return (
        "<h3>Pairwise drug-drug interactions (DDInter)</h3>"
        "<p>Source: DDInter v1 (<a href=\"https://ddinter.scbdd.com\">ddinter.scbdd.com</a>), "
        "CC BY-NC-SA 4.0. Severity (Major / Moderate / Minor) is curated by the "
        "DDInter team — confirm with the prescribing clinician.</p>"
        '<table class="data">'
        "<thead><tr><th>Pair</th><th>Severity</th><th>Notes</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def _overlaps_block(report: Dict[str, Any]) -> str:
    overlaps = report.get("target_overlaps") or []
    if not overlaps:
        return ""
    rows = []
    for r in overlaps:
        target = r.get("gene_symbol") or r.get("protein_name") or "shared target"
        action_a = (r.get("action_type_a") or "—").lower()
        action_b = (r.get("action_type_b") or "—").lower()
        rows.append(
            "<tr>"
            f"<td>{_escape(r.get('drug_a', ''))} ↔ {_escape(r.get('drug_b', ''))}</td>"
            f"<td><code>{_escape(target)}</code></td>"
            f"<td>{_escape(action_a)}</td>"
            f"<td>{_escape(action_b)}</td>"
            "</tr>"
        )
    return (
        "<h3>Mechanism / target overlap (ChEMBL)</h3>"
        "<p>Source: ChEMBL <code>mechanism</code> + "
        "<code>target</code> resources. Overlap on its own does not "
        "imply a problem — combination therapy is often intentional — "
        "but it's worth raising with the prescriber.</p>"
        '<table class="data">'
        "<thead><tr><th>Pair</th><th>Shared target</th>"
        "<th>Drug A action</th><th>Drug B action</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def _faers_block(report: Dict[str, Any]) -> str:
    matches = report.get("faers_symptom_matches") or []
    panels = report.get("faers_panels") or []
    if not matches and not panels:
        return ""
    pieces: List[str] = []
    pieces.append(
        "<h3>OpenFDA FAERS post-market reporting</h3>"
        "<p>Source: openFDA <code>/drug/event.json</code>. Reports are "
        "voluntary and do not establish causation; counts reflect what "
        "has been reported, not actual incidence.</p>"
    )
    if matches:
        rows = []
        for m in matches:
            rank = f"#{m['rank_in_top']}" if m.get("rank_in_top") is not None else "—"
            rows.append(
                "<tr>"
                f"<td>{_escape(m.get('drug_name', ''))}</td>"
                f"<td>{_escape(m.get('symptom', ''))}</td>"
                f"<td>{_escape(m.get('matched_term', ''))}</td>"
                f"<td>{rank}</td>"
                f"<td>{_format_count(m.get('count', 0))}</td>"
                f"<td>{_format_count(m.get('total_reports', 0))}</td>"
                "</tr>"
            )
        pieces.append(
            "<h4>Symptom → reaction matches</h4>"
            '<table class="data">'
            "<thead><tr>"
            "<th>Drug</th><th>Symptom</th><th>Matched FAERS term</th>"
            "<th>Rank in top reactions</th><th>Reports</th><th>Total reports for drug</th>"
            "</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            "</table>"
        )
    if panels:
        panel_html_parts: List[str] = []
        for panel in panels:
            top_events = (panel.get("top_events") or [])[:10]
            ev_rows = "".join(
                f"<tr><td>{_escape(ev.get('term', ''))}</td><td>{_format_count(ev.get('count', 0))}</td></tr>"
                for ev in top_events
            )
            if ev_rows:
                body = (
                    '<table class="data">'
                    "<thead><tr><th>Reaction term</th><th>Reports</th></tr></thead>"
                    f"<tbody>{ev_rows}</tbody>"
                    "</table>"
                )
            else:
                body = '<p class="muted"><em>No reports returned for this drug.</em></p>'
            panel_html_parts.append(
                f"<h4>{_escape(panel.get('drug_name', ''))} — "
                f"{_format_count(panel.get('total_reports', 0))} total reports</h4>"
                f"{body}"
            )
        pieces.append("<h4>Top reported reactions per drug</h4>" + "".join(panel_html_parts))
    return "".join(pieces)


def _deterministic_findings_section(report: Dict[str, Any]) -> str:
    blocks = [
        _merges_block(report.get("merge_notes") or []),
        _interactions_block(report),
        _overlaps_block(report),
        _faers_block(report),
    ]
    blocks = [b for b in blocks if b]
    if not blocks:
        return ""
    return (
        '<section class="section">'
        "<h2>2. Deterministic findings</h2>"
        '<p class="muted">'
        "Factual lookups produced before the LLM passes — sourced from "
        "RxNorm, DDInter, ChEMBL, and openFDA respectively. The audit "
        "synthesis (section 6) is instructed to repeat these verbatim "
        "rather than infer new ones."
        "</p>"
        f"{''.join(blocks)}"
        "</section>"
    )


_MODALITY_TERMS = {
    "radiation": "radiation therapy",
    "surgery": "surgery",
    "chemotherapy": "chemotherapy",
    "targeted": "targeted therapy",
}


def _modality_intervention_term(modality: str) -> str:
    return _MODALITY_TERMS.get((modality or "").lower(), modality or "")


def _methodology_section(report: Dict[str, Any]) -> str:
    plan = report.get("plan") or {}
    pdq = report.get("pdq_summary")
    summaries = report.get("source_summaries") or []
    summary_count = len(summaries)

    if pdq:
        if pdq.get("stage"):
            stage_line = f'Filtered for stage: <code>{_escape(pdq["stage"])}</code>'
        else:
            stage_line = "No stage filter applied."
        if pdq.get("stage_detail"):
            detail_line = (
                f' &nbsp;Stage-detail tokens scored against headings + body: '
                f'<code>{_escape(pdq["stage_detail"])}</code>.'
            )
        else:
            detail_line = ""
        section_titles = "".join(
            f'<li><code>{_escape(s.get("title", ""))}</code> (h{s.get("level", 2)})</li>'
            for s in (pdq.get("sections") or [])
        )
        pdq_block = (
            "<h3>NCI PDQ — Health Professional</h3>"
            f'<p>URL fetched: <a href="{_escape(pdq.get("source_url", ""))}">{_escape(pdq.get("source_url", ""))}</a></p>'
            f"<p>{stage_line}{detail_line}</p>"
            "<p>The page is parsed for <code>h2/h3/h4 + p/li</code>; sections are scored "
            "against (stage keywords, marker keywords, stage-detail tokens) with "
            'always-include for "stage information", "treatment option overview", '
            '"surgical treatment", "radiation therapy". Top-N kept, capped at '
            "6&nbsp;sections / 6,000&nbsp;chars total. Sections retained for this run:</p>"
            f"<ul>{section_titles}</ul>"
        )
    else:
        pdq_block = (
            "<h3>NCI PDQ — Health Professional</h3>"
            "<p>No PDQ summary available for this cancer type (hematologic / rare "
            "cancers are intentionally unmapped). Skipped.</p>"
        )

    modality_trials = report.get("modality_trials") or []
    modality_rows = []
    for entry in modality_trials:
        modality = entry.get("modality") or ""
        term = _modality_intervention_term(modality)
        count = len(entry.get("trials") or [])
        plural = "" if count == 1 else "s"
        modality_rows.append(
            "<tr>"
            f"<td><code>{_escape(modality)}</code></td>"
            f"<td><code>query.intr={_escape(term)}</code></td>"
            f"<td>{count} trial{plural} returned</td>"
            "</tr>"
        )
    condition_term = plan.get("subtype_display") or plan.get("subtype") or plan.get("cancer_type_display") or plan.get("cancer_type") or ""
    modality_block = (
        "<h3>ClinicalTrials.gov — modality search</h3>"
        "<p>For each of the four modalities (radiation, surgery, chemotherapy, "
        "targeted), a parallel CT.gov v2 query is run via <code>GET /studies</code> "
        "with these parameters:</p>"
        "<ul>"
        "<li><code>query.cond</code> = subtype's first ChEMBL indication term if "
        "present, else the subtype name (this run: "
        f"<code>{_escape(condition_term)}</code>; "
        "the backend resolves the exact term server-side).</li>"
        "<li><code>query.intr</code> = modality intervention term (see table below).</li>"
        "<li><code>filter.overallStatus</code> = <code>COMPLETED|TERMINATED|ACTIVE_NOT_RECRUITING</code>"
        " — completed trials with reportable outcomes are preferred over "
        "actively-recruiting trials.</li>"
        "<li><code>pageSize</code> = 100, up to 3 pages, hard-capped at 300 raw "
        "records before sort.</li>"
        "<li>Sort: trials with multi-arm reported numeric outcomes first "
        "(apples-to-apples comparisons), then any-results, then more arms, "
        "with NCT-ID as a stable tiebreak.</li>"
        "<li>No date-range filter is applied; ordering does the prioritization.</li>"
        "<li>Up to 8 trials per modality are returned to the audit pass.</li>"
        "</ul>"
        '<table class="data">'
        "<thead><tr><th>Modality</th><th>CT.gov intervention term</th><th>Result</th></tr></thead>"
        f"<tbody>{''.join(modality_rows)}</tbody>"
        "</table>"
    )

    drug_trials = report.get("drug_trials") or []
    drug_rows = []
    for entry in drug_trials:
        chembl = entry.get("chembl_id") or "—"
        count = len(entry.get("trials") or [])
        if not entry.get("chembl_id"):
            detail = "No ChEMBL ID — trial fetch skipped."
        elif count == 0:
            detail = "No trials returned."
        else:
            plural = "" if count == 1 else "s"
            detail = f"{count} trial{plural} returned"
        drug_rows.append(
            "<tr>"
            f"<td>{_escape(entry.get('drug_name', ''))}</td>"
            f"<td><code>{_escape(chembl)}</code></td>"
            f"<td>{_escape(detail)}</td>"
            "</tr>"
        )
    drug_rows_html = "".join(drug_rows) if drug_rows else '<tr><td colspan="3"><em>No drugs supplied.</em></td></tr>'
    drug_block = (
        "<h3>ClinicalTrials.gov — per-drug trials</h3>"
        "<p>For each prescribed drug with a ChEMBL ID, NCT IDs are pulled from "
        "ChEMBL's <code>drug_indication</code> records, then each trial is "
        "fetched from CT.gov v2 (<code>GET /studies/&lt;NCT&gt;</code>) in "
        "parallel (max 5 concurrent). The same multi-arm-results-first sort "
        "is applied. Up to 10 trials per drug are surfaced.</p>"
        '<table class="data">'
        "<thead><tr><th>Drug</th><th>ChEMBL ID</th><th>Result</th></tr></thead>"
        f"<tbody>{drug_rows_html}</tbody>"
        "</table>"
    )

    summary_plural = "y" if summary_count == 1 else "ies"
    n_drug_trials = len(drug_trials)
    overview = (
        "<h3>Multi-pass synthesis</h3>"
        "<p>The audit is intentionally split into many small LLM calls instead "
        "of one giant prompt — each source is summarized in isolation so a "
        "large source can't drown the others out, and the final synthesis "
        "reasons over the digests rather than the raw data:</p>"
        "<ol>"
        "<li><strong>Drug normalization.</strong> Each prescribed drug is "
        "resolved to an RxNorm ingredient RXCUI; brand-vs-generic "
        "duplicates are collapsed before any downstream fetch (issue #55). "
        "See section&nbsp;2 for the merges flagged for this run.</li>"
        "<li><strong>Deterministic safety lookups.</strong> Pairwise "
        "DDInter drug-drug interactions (issue&nbsp;#47), ChEMBL "
        "mechanism-of-action target overlap among prescribed drugs "
        "(issue&nbsp;#53), and openFDA FAERS top reactions plus "
        "symptom→reaction matching (issue&nbsp;#46). All factual, "
        "non-LLM-inferred — surfaced in section&nbsp;2 and fed "
        'verbatim to the synthesis prompt as labelled "do-not-invent" '
        "context.</li>"
        "<li><strong>Source fetch.</strong> PDQ summary (1 call), modality "
        "trials (4 parallel CT.gov queries), per-drug trials "
        f"({n_drug_trials} parallel CT.gov queries).</li>"
        "<li><strong>Per-source mini-summaries.</strong> Each non-empty source "
        "is run through Ollama with the patient plan as context, producing "
        "a 120–180 word digest pointed at this patient's subtype/stage. "
        f"{summary_count} mini-summar{summary_plural} produced for this run.</li>"
        "<li><strong>Final synthesis.</strong> A single Ollama call combines "
        "the patient plan (now including the deterministic findings "
        "from step&nbsp;2) + every mini-summary into the 350–550 word "
        "audit shown below, with explicit NCT-ID citations and a "
        '"Further reading" block. The raw source data is not in the '
        "synthesis prompt — the model only sees the mini-summaries it "
        "produced earlier and the deterministic-finding rows.</li>"
        "</ol>"
        "<p>This pipeline is fully reproducible by hand: pull the same PDQ page, "
        "run the same CT.gov queries listed above, query the same "
        "RxNorm / DDInter / ChEMBL / openFDA endpoints with the same "
        "inputs, then paste each source into an LLM with the patient "
        "plan and ask for the same digests.</p>"
    )

    return (
        '<section class="section">'
        "<h2>3. Methodology &amp; data sources</h2>"
        f"{overview}"
        f"{pdq_block}"
        f"{modality_block}"
        f"{drug_block}"
        "</section>"
    )


def _step_rendering(state: str, detail: Optional[str]):
    s = (state or "").lower()
    if s == "running":
        return ("step-running", "running", None)
    if s == "done":
        return ("step-done", "done", None)
    if s == "skipped":
        return ("step-skipped", "skipped", detail)
    if s == "failed":
        return ("step-failed", "failed", detail)
    return ("step-running", state or "?", detail)


def _pipeline_log_section(steps: List[Dict[str, Any]]) -> str:
    if not steps:
        return ""
    rows = []
    for step in steps:
        css_class, label, detail = _step_rendering(step.get("state", ""), step.get("detail"))
        detail_cell = f'<td class="muted">{_escape(detail)}</td>' if detail else "<td></td>"
        rows.append(
            "<tr>"
            f'<td class="{css_class}">{_escape(label)}</td>'
            f"<td>{_escape(step.get('label', ''))}</td>"
            f"{detail_cell}"
            "</tr>"
        )
    return (
        '<section class="section">'
        "<h2>4. Audit pipeline log</h2>"
        '<p class="muted">Live trace of fetches and LLM passes for this run.</p>'
        '<table class="data">'
        "<thead><tr><th>State</th><th>Step</th><th>Detail</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
        "</section>"
    )


def _source_summaries_section(summaries: List[Dict[str, Any]]) -> str:
    if not summaries:
        return (
            '<section class="section">'
            "<h2>5. Per-source summaries</h2>"
            '<p class="muted"><em>No per-source summaries were produced for this run.</em></p>'
            "</section>"
        )
    blocks = []
    for entry in summaries:
        blocks.append(
            '<div class="summary-block">'
            f'<div class="label">{_escape(entry.get("label", ""))}</div>'
            f'<div class="prose">{_paragraphs(entry.get("summary", ""))}</div>'
            "</div>"
        )
    return (
        '<section class="section">'
        "<h2>5. Per-source summaries</h2>"
        f"{''.join(blocks)}"
        "</section>"
    )


def _final_audit_section(text: Optional[str]) -> str:
    body_text = (text or "").strip()
    if not body_text:
        body = '<p class="muted"><em>The final synthesis was empty for this run.</em></p>'
    else:
        body = f'<div class="prose">{_paragraphs(text)}</div>'
    return (
        '<section class="section synthesis">'
        "<h2>6. Final audit</h2>"
        f"{body}"
        "</section>"
    )


def _reference_li(trial: Dict[str, Any], context: str) -> str:
    nct_id = trial.get("nct_id", "")
    url = f"https://clinicaltrials.gov/study/{nct_id}"
    title = trial.get("title")
    title_part = f" — {_escape(title)}" if title else ""
    return (
        f"<li><code>{_escape(nct_id)}</code>"
        f'<span class="muted"> ({_escape(context)})</span>: '
        f'<a href="{_escape(url)}">{_escape(url)}</a>{title_part}</li>'
    )


def _references_section(report: Dict[str, Any]) -> str:
    entries: List[str] = []
    pdq = report.get("pdq_summary")
    if pdq:
        slug_capitalized = (pdq.get("slug") or "").capitalize()
        entries.append(
            f"<li><strong>NCI PDQ — {_escape(slug_capitalized)} (Health Professional):</strong> "
            f'<a href="{_escape(pdq.get("source_url", ""))}">{_escape(pdq.get("source_url", ""))}</a></li>'
        )

    seen: set = set()
    nct_rows: List[str] = []
    for entry in report.get("modality_trials") or []:
        modality = (entry.get("modality") or "").capitalize()
        for trial in entry.get("trials") or []:
            nct_id = trial.get("nct_id")
            if not nct_id or nct_id in seen:
                continue
            seen.add(nct_id)
            nct_rows.append(_reference_li(trial, f"{modality} trial"))
    for entry in report.get("drug_trials") or []:
        drug_name = entry.get("drug_name") or ""
        for trial in entry.get("trials") or []:
            nct_id = trial.get("nct_id")
            if not nct_id or nct_id in seen:
                continue
            seen.add(nct_id)
            nct_rows.append(_reference_li(trial, f"{drug_name} trial"))
    if nct_rows:
        entries.append(
            f"<li><strong>ClinicalTrials.gov studies cited / surfaced ({len(nct_rows)}):</strong>"
            f'<ul class="references">{"".join(nct_rows)}</ul>'
            "</li>"
        )

    if report.get("drug_interactions"):
        entries.append(
            "<li><strong>DDInter drug-drug interactions:</strong> "
            '<a href="https://ddinter.scbdd.com">https://ddinter.scbdd.com</a> '
            "(CC BY-NC-SA 4.0).</li>"
        )
    if report.get("target_overlaps"):
        entries.append(
            "<li><strong>ChEMBL mechanism / target data:</strong> "
            '<a href="https://www.ebi.ac.uk/chembl/">https://www.ebi.ac.uk/chembl/</a> '
            "(<code>mechanism</code> + <code>target</code> resources).</li>"
        )
    if report.get("faers_symptom_matches"):
        entries.append(
            "<li><strong>OpenFDA FAERS adverse events:</strong> "
            '<a href="https://open.fda.gov/apis/drug/event/">https://open.fda.gov/apis/drug/event/</a></li>'
        )

    entries.append(
        "<li><strong>RxNorm (drug name normalization):</strong> "
        '<a href="https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html">'
        "https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html</a></li>"
    )
    entries.append(
        "<li><strong>Bio-Neighbor source &amp; methodology:</strong> "
        f'<a href="{REPO_URL}">{REPO_URL}</a></li>'
    )

    return (
        '<section class="section">'
        "<h2>7. References</h2>"
        f'<ul class="plain">{"".join(entries)}</ul>'
        "</section>"
    )


def _footer_section(timestamp: str) -> str:
    return (
        '<footer class="footer">'
        f"<p>Generated by Bio-Neighbor Treatment Auditor on {_escape(timestamp)}.</p>"
        f'<p>Repository: <a href="{REPO_URL}">{REPO_URL}</a></p>'
        "<p>Research tool only. Not medical advice. Discuss any plan changes with your oncology team.</p>"
        "</footer>"
    )


# --- public API -------------------------------------------------------------

def build_html(report: Dict[str, Any]) -> str:
    """Assemble the report HTML. `report` is a `ReportPayload` dict — see
    issue #67 for the wire format. Every section past `plan` is optional and
    is elided gracefully when absent."""
    plan = report.get("plan") or {}
    if not plan:
        raise ValueError("report.plan is required")
    timestamp = _iso_timestamp(report.get("generated_at"))
    body_parts = [
        _header_section(timestamp),
        _disclaimer_section(),
        _inputs_section(plan),
        _deterministic_findings_section(report),
        _methodology_section(report),
        _pipeline_log_section(report.get("steps") or []),
        _source_summaries_section(report.get("source_summaries") or []),
        _final_audit_section(report.get("final_audit")),
        _references_section(report),
        _footer_section(timestamp),
    ]
    body = "".join(body_parts)
    return (
        "<!DOCTYPE html>"
        '<html lang="en">'
        "<head>"
        '<meta charset="utf-8">'
        "<title>Treatment Auditor Report</title>"
        f"<style>{STYLESHEET}</style>"
        "</head>"
        f"<body>{body}</body>"
        "</html>"
    )


def render_pdf(html: str) -> bytes:
    """Render `html` (from `build_html`) to a paginated PDF."""
    return weasyprint.HTML(string=html).write_pdf()
